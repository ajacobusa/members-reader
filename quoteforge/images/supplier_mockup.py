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
        t = g.garment_type
        if t in out or getattr(g, "tier", "Classic") != "Classic":
            continue
        if not (g.sizes and g.colors):
            continue
        sku = apparel_sku_for(g.garment_id, g.sizes[0], g.colors[0])
        if not sku:
            continue
        url = gelato_blank_image(sku, refresh=refresh)
        if url:
            out[t] = url
    return out
