"""Auto-pull official product images from the Gelato ECOMMERCE store (#180).

This removes the manual "owner creates a product -> tell me -> I wire it" handoff:
a daily job polls the connected Gelato ecommerce store, and the moment a product
exists it pulls that product's real mockup image (``previewUrl``) and maps it back
to our SKU, so the storefront shows the genuine product with zero further action.

Grounded facts this is built on (verified live, read-only):
  * The store is connected: ``GET ecommerce.gelatoapis.com/v1/stores`` -> 200, one
    store ``type:"etsy"`` (id in ``GELATO_STORE_ID``). ``/products`` -> ``{"products":[]}``
    (empty today, so this is a safe no-op until the owner creates the first product).
  * The ecommerce host is behind Cloudflare and **rejects requests without a browser
    ``User-Agent``** (403 ``error code 1010``) — so every call here sends one.
  * The exact object that holds ``previewUrl`` (top-level vs per-variant/mockup) is
    documented but **could not be observed against a real product** (0 products). So
    extraction is DEFENSIVE: it reuses ``_extract_image_url`` (handles several shapes)
    and, when it can't confidently pull/join, it SKIPS (safe) and records the raw
    product keys in ``status()`` so the real shape is self-reported, not guessed.

Guard rails (non-negotiable):
  * No-op unless genuinely live: TEST_MODE, or no ``GELATO_API_KEY``, or no
    ``GELATO_STORE_ID`` -> returns ``{}`` / empty; the storefront keeps its generated
    tile. Never raises (a network/shape blip must never break a rebuild).
  * Conservative join: a store product maps to our SKU only via a confident key
    (our SKU carried as ``externalId``/``externalProductId``, or a Gelato product UID
    that reverse-resolves through ``_uid_map``). Ambiguous -> skipped, never guessed
    (a wrong map would show the wrong product image).
  * Customer-safe: this returns the raw S3 ``previewUrl``; the caller re-hosts it
    same-origin (``listing_preview._emit_url``) before it reaches the page — the
    supplier/marketplace origin is never emitted.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Browser UA is REQUIRED — the ecommerce host's Cloudflare returns 403 (code 1010)
# without it (verified live). Kept generic; carries no identifying info.
_UA = "Mozilla/5.0 (compatible; QuoteForge/1.0)"


def _gate() -> tuple[bool, str]:
    """(enabled, store_id). Enabled only when genuinely live AND a store id is set."""
    try:
        from quoteforge.config import TEST_MODE, GELATO_STORE_ID
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        sid = (GELATO_STORE_ID or "").strip()
        return (bool((not TEST_MODE) and GELATO_API_KEY and sid), sid)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ecommerce gate read failed: %s", exc)
        return (False, "")


def _ecom_get(path: str) -> Any | None:
    """Read-only GET against the ecommerce API (or None). Never raises.

    Sends X-API-KEY + the required browser User-Agent. ``path`` is appended to the
    ecommerce base + version (e.g. ``/stores/<id>/products``)."""
    enabled, _sid = _gate()
    if not enabled:
        return None
    try:
        import requests
        from quoteforge.config import GELATO_ECOMMERCE_URL
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        r = requests.get(
            f"{GELATO_ECOMMERCE_URL}/v1{path}",
            headers={"X-API-KEY": GELATO_API_KEY, "User-Agent": _UA,
                     "Content-Type": "application/json"},
            timeout=20)
        if r.status_code != 200:
            logger.debug("ecommerce GET %s -> %s", path, r.status_code)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001 — never break a rebuild on a network blip
        logger.debug("ecommerce GET %s failed: %s", path, exc)
        return None


def store_products() -> list[dict]:
    """Every product in the connected store (or [] when empty / not live)."""
    _e, sid = _gate()
    if not sid:
        return []
    data = _ecom_get(f"/stores/{sid}/products")
    prods = (data or {}).get("products") if isinstance(data, dict) else None
    return prods if isinstance(prods, list) else []


def template_previews(getter=None) -> list[dict]:
    """The store's templates with their mockup previewUrl - the EARLIEST documented real
    product image (a template exists before any product/listing is published; per Gelato's
    Get Template API the response carries a previewUrl).

    Returns ``[{template_id, title, preview_url}]``, [] when not live / no store / no
    templates. Provenance-honest: a template preview is NOT yet bound to a SKU/UID (the
    join is owner-confirmed when the product is created from it), so consumers treat it as
    display-candidate only - it can never publish through Path A without the UID gate.
    ``getter(path)->json`` is injectable for hermetic tests (defaults to _ecom_get)."""
    _e, sid = _gate()
    if not sid:
        return []
    get = getter if getter is not None else _ecom_get
    data = get(f"/stores/{sid}/templates")
    rows = (data.get("templates") or data.get("data") if isinstance(data, dict)
            else data) or []
    out: list[dict] = []
    for t in rows:
        if not isinstance(t, dict):
            continue
        tid = t.get("id") or t.get("templateId") or t.get("uid")
        url = (t.get("previewUrl") or t.get("preview_url")
               or _extract_preview(t))
        if tid and url:
            out.append({"template_id": str(tid), "title": t.get("title") or "",
                        "preview_url": url})
    return out


def _extract_preview(t: dict) -> str | None:
    """Best-effort previewUrl from a template's variants (shape self-reported at live)."""
    for v in (t.get("variants") or []):
        if isinstance(v, dict):
            for iv in (v.get("imagePlaceholders") or []):
                u = isinstance(iv, dict) and iv.get("previewUrl")
                if u:
                    return u
            u = v.get("previewUrl")
            if u:
                return u
    return None


def _product_detail(sid: str, product_id: str) -> dict:
    """One store product's full record (the mockup ``previewUrl`` lives here)."""
    d = _ecom_get(f"/stores/{sid}/products/{product_id}")
    return d if isinstance(d, dict) else {}


def _sku_for(product: dict, uid_to_sku: dict) -> str | None:
    """Confidently map a store product back to OUR sku, or None (skip).

    Priority: our SKU carried as an external id -> then a Gelato product UID that
    reverse-resolves through the SKU->UID map. Anything ambiguous returns None so a
    wrong image is never shown."""
    for key in ("externalId", "externalProductId", "storeProductId"):
        v = product.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # variant-level Gelato UID -> our SKU (only if the UID map is populated)
    for var in (product.get("variants") or []):
        if not isinstance(var, dict):
            continue
        uid = var.get("productUid") or var.get("uid")
        if isinstance(uid, str) and uid in uid_to_sku:
            return uid_to_sku[uid]
    return None


_IMG_CACHE: dict | None = None


def images_by_sku(*, refresh: bool = False) -> dict:
    """{our_sku -> previewUrl} for every store product we can confidently map.

    Memoized per process (a rebuild calls this once per SKU) — pass ``refresh=True``
    to re-fetch. Empty when not live / store empty / nothing confidently joins.
    Never raises."""
    global _IMG_CACHE
    if _IMG_CACHE is not None and not refresh:
        return _IMG_CACHE
    _IMG_CACHE = _compute_images_by_sku()
    return _IMG_CACHE


def _compute_images_by_sku() -> dict:
    """Uncached build of {our_sku -> previewUrl}. See images_by_sku()."""
    _e, sid = _gate()
    if not sid:
        return {}
    prods = store_products()
    if not prods:
        return {}
    try:
        # Collision-safe inversion (#uidjoin): a UID shared by 2 of our SKUs is SKIPPED,
        # never guessed - else a store product's photo lands on the wrong SKU's tile.
        from quoteforge.automation.gelato_sync import invert_uid_map
        uid_to_sku = invert_uid_map()
    except Exception as exc:  # noqa: BLE001
        logger.debug("uid map read failed: %s", exc)
        uid_to_sku = {}
    from quoteforge.images.supplier_mockup import _extract_image_url
    out: dict = {}
    for p in prods:
        if not isinstance(p, dict):
            continue
        pid = p.get("id") or p.get("productId")
        sku = _sku_for(p, uid_to_sku)
        if not sku:
            continue
        detail = _product_detail(sid, str(pid)) if pid else p
        url = _extract_image_url(detail) or _extract_image_url(p)
        if url:
            out[sku] = url
    return out


def status() -> dict:
    """Self-diagnosing snapshot for the daily report + infra-check. Never raises.

    Reports enabled state, product count, how many mapped to a SKU with an image,
    and — when products exist but don't map — a SAMPLE of the raw product keys so the
    real ``previewUrl``/join shape is surfaced (not guessed) for finalising the wiring."""
    enabled, sid = _gate()
    if not enabled:
        return {"enabled": False, "store_id": sid, "products": 0,
                "mapped": 0, "reason": "TEST_MODE / no key / no GELATO_STORE_ID"}
    prods = store_products()
    mapped = images_by_sku()
    sample_keys: list[str] = []
    if prods and not mapped and isinstance(prods[0], dict):
        sample_keys = sorted(prods[0].keys())
    return {"enabled": True, "store_id": sid, "products": len(prods),
            "mapped": len(mapped),
            "unmapped_sample_keys": sample_keys}
