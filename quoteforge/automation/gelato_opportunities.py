"""Product-opportunity agent: continuously surface NEW products/sizes the print
partner offers that we DON'T sell yet, so the catalog keeps growing.

Where `gelato_catalog_review` watches for new/discontinued *catalogs*, this is the
*product expert*: within the departments we already sell, it diffs the print
partner's available sizes/variants against ours and reports the gap (e.g. a 10oz-slim
mug, a 3XL tee) as an expansion opportunity. Report-only - it never changes the
catalog; the owner decides what to add. All network is injected for tests.
"""
from __future__ import annotations

# department -> (catalogUid, size attribute) used to read the partner's offered sizes
DEPT_SIZE_ATTR: dict[str, tuple[str, str]] = {
    "mug": ("mugs", "MugSize"),
    "apparel": ("t-shirts", "GarmentSize"),
    "poster": ("posters", "UnifiedPaperFormat"),
    "canvas": ("canvas", "CanvasFormat"),
    "acrylic": ("acrylic", "AcrylicFormat"),
    "metal": ("metallic", "MetallicFormat"),
}


def _norm(s) -> str:
    """Canonicalise a size token for comparison ('11-oz' -> '11oz', 'S' -> 's')."""
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def find_opportunities(our_sizes: dict, gelato_sizes: dict) -> dict:
    """Pure diff. ``our_sizes`` / ``gelato_sizes`` = {dept: set(raw size tokens)}.

    Returns {dept: {have:[...], could_add:[...]}} for departments where the partner
    offers a size we don't carry. A partner size counts as 'have' if any of our size
    tokens normalises to match (exact or substring, so '8x10' matches the partner's
    '8x10-inch-200x250-mm').
    """
    out: dict = {}
    for dept, gset in gelato_sizes.items():
        ours = our_sizes.get(dept) or set()
        ours_norm = {_norm(x) for x in ours}
        could = []
        for g in sorted(gset):
            gn = _norm(g)
            if not gn:
                continue
            # Exact match, or a substring match ONLY for tokens >=4 chars - so our
            # '8x10' matches the partner's verbose '8x10-inch-200x250-mm', but short
            # apparel sizes don't false-match ('xl' must NOT count as having '3xl').
            have = any(
                gn == o
                or (len(o) >= 4 and o in gn)
                or (len(gn) >= 4 and gn in o)
                for o in ours_norm if o)
            if not have:
                could.append(g)
        if could:
            out[dept] = {"have": sorted(ours), "could_add": could}
    return out


def format_opportunities(res: dict) -> str:
    """Owner-facing report of expansion opportunities."""
    if not res:
        return ("PRODUCT OPPORTUNITIES\n" + "=" * 40 +
                "\nNo new sizes to add - our catalog matches what the partner offers.")
    lines = ["PRODUCT OPPORTUNITIES", "=" * 40,
             "Sizes/variants the print partner offers that we don't sell yet:", ""]
    for dept, d in sorted(res.items()):
        lines.append(f"{dept.upper()} - could add {len(d['could_add'])}:")
        lines.append("  + " + ", ".join(d["could_add"]))
        lines.append(f"    (we have: {', '.join(d['have']) or 'none'})")
        lines.append("")
    lines.append("Report only - price-check each against the 60% margin floor before "
                 "adding. Nothing was changed.")
    return "\n".join(lines)


def our_inventory() -> dict:
    """Build {dept: set(size tokens we currently sell)} from our catalogs."""
    inv: dict = {}
    try:
        from quoteforge.etsy.mug_catalog import MUG_CATALOG
        inv["mug"] = {s for m in MUG_CATALOG for s in getattr(m, "sizes", [])}
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
        inv["apparel"] = {s for g in APPAREL_CATALOG for s in getattr(g, "sizes", [])}
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
        for p in GELATO_CATALOG:
            if p.category in ("poster", "canvas", "acrylic", "metal"):
                inv.setdefault(p.category, set()).add(str(p.size).split()[0])
    except Exception:  # noqa: BLE001
        pass
    return inv


def gelato_catalog_sizes(catalog: str, size_attr: str) -> set:
    """Live: the size-attribute values the partner offers for a catalog (read-only)."""
    import requests
    from quoteforge.config import GELATO_API_KEY
    r = requests.post(
        f"https://product.gelatoapis.com/v3/catalogs/{catalog}/products:search",
        headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
        json={"limit": 1}, timeout=25)
    hits = (r.json() or {}).get("hits") or {}
    attrs = hits.get("attributeHits", {}) if isinstance(hits, dict) else {}
    return set((attrs.get(size_attr) or {}).keys())


def review_opportunities(fetch_sizes=gelato_catalog_sizes,
                         dept_attr: dict | None = None) -> dict:
    """Live: build our inventory, read the partner's sizes, return the opportunity gap."""
    dept_attr = dept_attr or DEPT_SIZE_ATTR
    ours = our_inventory()
    gel: dict = {}
    for dept, (catalog, attr) in dept_attr.items():
        try:
            gel[dept] = fetch_sizes(catalog, attr)
        except Exception:  # noqa: BLE001
            gel[dept] = set()
    return find_opportunities(ours, gel)
