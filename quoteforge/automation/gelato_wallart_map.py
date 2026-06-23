"""Map the Wall-Art products (poster/canvas/framed/acrylic/metal) to REAL Gelato
product UIDs, replacing the GEL-* placeholder SKUs that block go-live.

Wall art uses the static `our_sku -> uid` map (gelato_sync._uid_map / GELATO_UID_MAP)
rather than the per-variant family map. This builds that map by querying the live
catalog, size by size, and picking a sensible default variant (portrait, standard
paper/material). Every UID returned is a REAL catalog UID (we only ever pick from
what the API returns) - it is a DRAFT for owner review + one test order per material,
never a go-live switch. Network is injected for tests.
"""
from __future__ import annotations

# category -> (catalogUid, material-keyword prefs, size-filter attribute, token style)
# token style 'full' = '8x10-inch-200x250-mm' (posters/framed share UnifiedPaperFormat);
# 'short' = '8x10-inch' (canvas/acrylic/metal each have their own *Format attribute).
CATEGORY_PLAN: dict[str, tuple[str, tuple[str, ...], str, str]] = {
    "poster": ("posters", ("coated-silk", "170-gsm"), "UnifiedPaperFormat", "full"),
    "canvas": ("canvas", ("wood-fsc-thick", "canvas"), "CanvasFormat", "short"),
    "framed": ("framed-posters", ("black_wood", "coated-silk"),
               "UnifiedPaperFormat", "full"),
    "acrylic": ("acrylic", ("4-mm",), "AcrylicFormat", "short"),
    "metal": ("metallic", ("3-mm",), "MetallicFormat", "short"),
}

# leading size token -> full 'inch-mm' form (the 'short' form is just '<size>-inch')
SIZE_FMT: dict[str, str] = {
    "8x10": "8x10-inch-200x250-mm",
    "11x14": "11x14-inch-270x350-mm",
    "12x16": "12x16-inch-300x400-mm",
    "16x20": "16x20-inch-400x500-mm",
    "18x24": "18x24-inch-450x600-mm",
    "24x36": "24x36-inch-600x900-mm",
}


def _size_key(size: str) -> str:
    """Normalise our size label ('8x10 in') to its leading token ('8x10')."""
    return (size or "").strip().split()[0] if size else ""


def pick_wallart_uid(product_uids: list[str], keywords: tuple[str, ...]) -> str | None:
    """Pick the best UID: most preferred-keyword hits, portrait (_ver) as default.

    Avoids 'brushed'/'grain' specialty finishes unless asked. Returns None if empty.
    """
    if not product_uids:
        return None

    def score(uid: str) -> tuple:
        """Rank a UID by keyword hits, plain finish, then portrait orientation."""
        u = uid.lower()
        hits = sum(1 for k in keywords if k.lower() in u)
        portrait = 1 if u.endswith("_ver") else 0
        plain = 0 if ("brushed" in u or "grain" in u) else 1
        return (hits, plain, portrait, -len(uid))

    return max(product_uids, key=score)


def build_wallart_map(fetch_products, catalog_iter=None) -> dict:
    """Build {our_sku -> real_uid} for every wall-art product.

    ``fetch_products(catalog_uid, size_fmt) -> list[str]`` returns candidate
    productUids for that catalog filtered to the size. Returns
    {map, unmapped, mapped_count, total}.
    """
    if catalog_iter is None:
        from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
        catalog_iter = GELATO_CATALOG
    out, unmapped = {}, []
    total = 0
    for p in catalog_iter:
        plan = CATEGORY_PLAN.get(getattr(p, "category", ""))
        if not plan:
            continue
        total += 1
        catalog_uid, keywords, size_attr, style = plan
        skey = _size_key(getattr(p, "size", ""))
        token = SIZE_FMT.get(skey) if style == "full" else (f"{skey}-inch" if skey
                                                             else None)
        sku = getattr(p, "gelato_sku", "")
        if not token or not sku:
            unmapped.append(sku or p.product_id)
            continue
        try:
            uids = fetch_products(catalog_uid, size_attr, token)
        except Exception:  # noqa: BLE001
            uids = []
        uid = pick_wallart_uid(uids, keywords)
        if uid:
            out[sku] = uid
        else:
            unmapped.append(sku)   # size not offered by Gelato for this material
    return {"map": out, "unmapped": unmapped,
            "mapped_count": len(out), "total": total}


def gelato_fetch_wallart(catalog_uid: str, size_attr: str, token: str,
                         limit: int = 60) -> list[str]:
    """Live: productUids in a catalog filtered to one size attribute (read-only)."""
    import requests
    from quoteforge.config import GELATO_API_KEY
    r = requests.post(
        f"https://product.gelatoapis.com/v3/catalogs/{catalog_uid}/products:search",
        headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
        json={"limit": limit, "attributeFilters": {size_attr: [token]}},
        timeout=30)
    prods = (r.json() or {}).get("products") or []
    return [p.get("productUid") for p in prods if p.get("productUid")]
