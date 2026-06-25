"""Supplier product mockups — real product images for the storefront.

Pulls the actual product image the print partner ships for a garment, so a tile
can show what the customer receives instead of an AI approximation. Key-gated and
TEST_MODE-safe: with no API key or in TEST_MODE this returns None and the caller
falls back to the existing AI tile. Resolved URLs are cached to a JSON file so a
rebuild does not re-hit the API. It activates automatically once the owner sets
the key and maps real product UIDs (a placeholder GEL-* UID is treated as
unmapped, exactly like the go-live guard).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_PRODUCT_API = "https://product.gelatoapis.com/v3/products"


def _cache_path() -> Path:
    """Where resolved SKU->image-URL mappings are cached between rebuilds."""
    p = os.getenv("GELATO_MOCKUP_CACHE", "").strip()
    if p:
        return Path(p)
    from quoteforge.config import OUTPUT_DIR
    return Path(OUTPUT_DIR) / "gelato_mockups.json"


def _load_cache() -> dict:
    """Load the SKU->URL cache (empty dict if missing/unreadable)."""
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    """Persist the SKU->URL cache; best-effort, never raises."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _extract_image_url(data: dict) -> str | None:
    """Best-effort pull of a product preview/mockup image URL from a product API
    response. The field name varies across catalog products, so try the common
    shapes (flat url field, or the first entry of an images/mockups list)."""
    if not isinstance(data, dict):
        return None
    for key in ("previewUrl", "mockupUrl", "productImageUrl", "imageUrl", "image"):
        v = data.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    imgs = data.get("images") or data.get("mockups")
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            for k in ("url", "previewUrl", "fileUrl", "imageUrl"):
                u = first.get(k)
                if isinstance(u, str) and u.startswith("http"):
                    return u
    return None


def _fetch_product_image(uid: str) -> str | None:
    """Live: one product's preview image URL (or None). Never raises."""
    import requests
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    try:
        r = requests.get(f"{_PRODUCT_API}/{uid}",
                         headers={"X-API-KEY": GELATO_API_KEY}, timeout=15)
        if r.status_code != 200:
            return None
        return _extract_image_url(r.json())
    except Exception:  # noqa: BLE001 — network/parse blip: fall back to AI tile
        return None


def gelato_blank_image(our_sku: str, *, refresh: bool = False) -> str | None:
    """Real product image URL for our SKU, or None to fall back to the AI tile.

    Returns None in TEST_MODE, without an API key, or for an unmapped / placeholder
    (GEL-*) UID — so nothing changes until the owner is genuinely live. Results are
    cached to JSON so a rebuild doesn't re-hit the API (pass refresh=True to force).
    """
    from quoteforge.config import TEST_MODE
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    if TEST_MODE or not GELATO_API_KEY:
        return None
    from quoteforge.automation.gelato_sync import _uid_map
    uid = (_uid_map() or {}).get(our_sku)
    if not uid or str(uid).startswith("GEL-"):     # unmapped / placeholder seed
        return None
    cache = _load_cache()
    if not refresh and our_sku in cache:
        return cache[our_sku] or None
    url = _fetch_product_image(uid)
    cache[our_sku] = url or ""
    _save_cache(cache)
    return url


def gelato_template_printarea(uid: str) -> dict | None:
    """Print placement for a product UID, as a fraction-of-photo rect for the mockup
    sync: ``{area:[x,y,w,h], cyl, span}`` or None.

    Gelato's Get-Template API exposes per-variant image placeholders with a
    ``printArea`` + ``height``/``width``. Mapping those onto the *mockup photo's*
    pixel rect is account/template-specific, so this is the documented seam:
    key-gated, returns None until the mapping is calibrated against a live account
    (the engine then falls back to the per-category geometry default, and the
    gelato-mockup-reviewer agent flags any product whose default is off). Never
    raises."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        if TEST_MODE or not GELATO_API_KEY or not uid or str(uid).startswith("GEL-"):
            return None
    except Exception:  # noqa: BLE001
        return None
    # TODO(calibrate-with-live): fetch the template, read printArea/dims, map to the
    # mockup-photo fraction rect. Until then the per-category default is used.
    return None


def apparel_tile_images(*, refresh: bool = False) -> dict:
    """Map garment_type -> real product image URL, one representative SKU per type
    (Classic tier, first colour/size). Only types that resolve to a real image are
    included; everything else stays on the AI tile. Empty in TEST_MODE / no key."""
    out: dict = {}
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        if TEST_MODE or not GELATO_API_KEY:
            return out
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
    except Exception:  # noqa: BLE001
        return out
    for g in APPAREL_CATALOG:
        if not (g.sizes and g.colors):
            continue
        sku = apparel_sku_for(g.garment_id, g.sizes[0], g.colors[0])
        if not sku:
            continue
        url = gelato_blank_image(sku, refresh=refresh)
        if url:
            out[g.garment_id] = url             # PER GARMENT (tier/gender-exact)
    return out


def apparel_tile_color_images(*, refresh: bool = False) -> dict:
    """Map garment_id -> {colour -> real product image URL}, so each tile/editor
    shows the EXACT product for that garment (tier + gender) in the picked colour.
    One representative SKU per (garment, colour). Empty in TEST_MODE / no key (the
    tile keeps its default photo)."""
    out: dict = {}
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        if TEST_MODE or not GELATO_API_KEY:
            return out
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
    except Exception:  # noqa: BLE001
        return out
    for g in APPAREL_CATALOG:
        if not (g.sizes and g.colors):
            continue
        per_color: dict = {}
        for color in g.colors:
            sku = apparel_sku_for(g.garment_id, g.sizes[0], color)
            if sku:
                url = gelato_blank_image(sku, refresh=refresh)
                if url:
                    per_color[color] = url
        if per_color:
            out[g.garment_id] = per_color        # PER GARMENT (tier/gender-exact)
    return out


def _gelato_create_design_mockup(product_uid: str, design_url: str) -> str | None:
    """Ask Gelato to render the buyer's DESIGN on the product, returning the
    mockup image URL. DEFENSIVE provider seam: never raises, returns None on
    anything unexpected. Confirm the exact endpoint/shape against a live account
    (the design must be a URL Gelato can fetch - i.e. print-file hosting set up)."""
    import requests
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    try:
        resp = requests.post(
            f"{_PRODUCT_API}/mockups",
            headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
            json={"productUid": product_uid,
                  "files": [{"type": "default", "url": design_url}]},
            timeout=45)
        if resp.status_code not in (200, 201):
            return None
        return _extract_image_url(resp.json())
    except Exception:  # noqa: BLE001 — any failure -> fall back to the flat artwork
        return None


def design_mockup_for_order(order: dict, design_path: str = None) -> str | None:
    """Real product mockup of the BUYER'S design on the ordered garment, for the
    customer proof.

    GUARDRAILS: key-gated + TEST_MODE-safe + ADDITIVE. Returns None (so the proof
    falls back to the flat artwork) in TEST_MODE, without a key, for a non-apparel
    order, with no resolvable garment UID, or on any failure. It is purely a visual
    aid in the proof - it does NOT change the print file and cannot bypass the
    customer's proof approval (the parity-gate hash still fingerprints the real
    artwork). Never raises.
    """
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        if TEST_MODE or not GELATO_API_KEY or not isinstance(order, dict):
            return None
        if order.get("product_type") != "apparel":
            return None
        uid = order.get("gelato_product_uid")
        if not uid:
            from quoteforge.etsy.apparel_catalog import resolve_apparel_uid
            uid = resolve_apparel_uid(order.get("gelato_sku"))
        design = design_path or order.get("artwork_url") or ""
        # Gelato must be able to FETCH the design - a local path can't be mocked up.
        if not uid or not str(design).lower().startswith(("http://", "https://")):
            return None
        return _gelato_create_design_mockup(uid, design)
    except Exception:  # noqa: BLE001
        return None
