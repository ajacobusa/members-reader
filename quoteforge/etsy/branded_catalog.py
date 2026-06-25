"""Custom Branded Products family (Gelato-fulfilled).

A self-contained parallel module modeled on apparel_catalog.py. Branded merch
differs from apparel only in shape:
  * one product line per item (no gender x tier explosion); each item is one
    listing with its own print bound (branded_dimensions_for).
  * variants are (size/variant x colour); flat products are size "One Size".
Costs are seeded (modeled) and overridden live by the Gelato sync; pricing always
re-derives from current cost to hold the 60% net-margin floor. Seed SKUs ship as
GEL-* placeholders mapped to real Gelato UIDs before go-live (verify_branded_mappings).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BRANDED_DIMS: tuple[int, int] = (3000, 3000)


@dataclass
class BrandedProduct:
    """One sellable branded product line with its sizes, colours, print geometry,
    seed cost and recommended Gelato blank."""
    product_id: str
    name: str
    type_name: str
    category: str
    sizes: list[str]
    colors: list[str]
    base_cost: float
    sku_prefix: str
    brand: str = ""
    tier: str = "Classic"
    width_px: int = DEFAULT_BRANDED_DIMS[0]
    height_px: int = DEFAULT_BRANDED_DIMS[1]
    placement: str = "front"


_BRANDED_TYPES = [
    ("tote", "Organic Cotton Tote Bag", "Tote Bag", "Bags",
     ["One Size"], ["Natural", "White", "Sand", "Sage", "Navy", "Black"],
     7.0, "Gelato Organic Tote", "Value", 3000, 3600),
    ("bottle", "Insulated Stainless Water Bottle", "Water Bottle", "Drinkware",
     ["20oz"], ["White", "Silver", "Black", "Navy", "Red"],
     12.0, "Gelato Steel Bottle", "Premium", 3600, 2400),
    ("tumbler", "Insulated Stainless Tumbler", "Tumbler", "Drinkware",
     ["20oz", "30oz"], ["White", "Silver", "Black", "Navy", "Forest Green"],
     14.0, "Gelato Steel Tumbler", "Premium", 3600, 2200),
    ("mousepad", "Rectangular Mouse Pad", "Mouse Pad", "Desk",
     ["9x7", "12x10"], ["White"], 6.0, "Gelato Mouse Pad", "Value", 2700, 2100),
    ("notebook", "Softcover Notebook", "Notebook", "Stationery",
     ["A5"], ["White", "Cream", "Black", "Navy"], 5.0, "Gelato Softcover", "Value", 1740, 2490),
    ("journal", "Hardcover Journal", "Journal", "Stationery",
     ["A5"], ["Black", "Navy", "Maroon", "Forest Green", "Sand"],
     9.0, "Gelato Hardcover", "Premium", 1740, 2490),
    ("sticker", "Die-Cut Vinyl Sticker", "Sticker", "Stickers",
     ["2x2", "3x3", "4x4"], ["White"], 2.0, "Gelato Vinyl Sticker", "Value", 1200, 1200),
    ("phonecase", "Tough Phone Case", "Phone Case", "Tech",
     ["iPhone", "Samsung"], ["White", "Black"], 8.0, "Gelato Tough Case", "Classic", 1800, 3600),
    ("keychain", "Metal Keychain", "Keychain", "Accessories",
     ["Rectangle", "Circle"], ["Silver"], 4.0, "Gelato Metal Keychain", "Value", 600, 600),
]


def _build_catalog() -> list[BrandedProduct]:
    """Build the branded product catalog from the type spec, one line per item."""
    out: list[BrandedProduct] = []
    for pid, name, type_name, cat, sizes, colors, cost, brand, tier, w, h in _BRANDED_TYPES:
        out.append(BrandedProduct(
            product_id=pid, name=name, type_name=type_name, category=cat,
            sizes=list(sizes), colors=list(colors), base_cost=cost,
            sku_prefix=f"GEL-{pid.upper()}", brand=brand, tier=tier,
            width_px=w, height_px=h))
    return out


BRANDED_CATALOG: list[BrandedProduct] = _build_catalog()


@dataclass
class BrandedVariant:
    """One sellable branded product/size/colour combination with cost and floor price."""
    product_id: str
    name: str
    size: str
    color: str
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    placement: str = "front"


def get_product(product_id: str) -> BrandedProduct | None:
    """Find a branded product by id (case-insensitive), or None."""
    key = (product_id or "").strip().lower()
    return next((p for p in BRANDED_CATALOG if p.product_id == key), None)


# Products that stay in the catalogue (for go-live mapping + tracking) but must
# NOT be sold yet because they can't be fulfilled correctly. A phone case offers
# only a generic "iPhone"/"Samsung" axis with no actual MODEL, so a single family
# UID would print a case that physically doesn't fit most buyers' phones. Until a
# per-model picker + per-model UIDs exist it is hidden from the storefront and can
# never resolve a routing SKU. Remove from this set to re-enable.
NON_SELLABLE_BRANDED = frozenset({"phonecase"})


def branded_sellable(product_id: str) -> bool:
    """True if this branded product may be shown + sold (not a known-unfulfillable
    line). Single source of truth for both the storefront grid and SKU routing."""
    return (product_id or "").strip().lower() not in NON_SELLABLE_BRANDED


def branded_dimensions_for(product_id: str) -> tuple[int, int]:
    """(width_px, height_px) of the print area for a branded product, or a safe default.

    The design editor reads this to bound branded art to the printable region
    instead of the full poster canvas."""
    p = get_product(product_id)
    return (p.width_px, p.height_px) if p else DEFAULT_BRANDED_DIMS


def _variant_sku(p: BrandedProduct, size: str, color: str) -> str:
    """Stable per-variant SKU, e.g. GEL-TOTE-ONE-SIZE-NATURAL."""
    part = lambda s: s.upper().replace(" ", "-")
    return f"{p.sku_prefix}-{part(size)}-{part(color)}"


def _variant_cost(p: BrandedProduct, sku: str) -> float | None:
    """Seed base cost, with any live Gelato override applied.

    Returns None when the live sync has marked the variant discontinued."""
    from quoteforge.etsy.catalog_state import sku_override
    ov = sku_override(sku)
    if ov and ov.get("available") is False:
        return None
    if ov and ov.get("cost") is not None:
        return round(ov["cost"], 2)
    return round(p.base_cost, 2)


def _list_floor(floor_pct: float | None) -> float:
    """The branded anchor margin: the LIST target, never below the 60% floor.
    The global TARGET_MARGIN_PCT is an ABSOLUTE floor even if a lower override is
    passed, mirroring the apparel + print variations."""
    from quoteforge.config import LIST_MARGIN_PCT, TARGET_MARGIN_PCT
    if floor_pct is not None:
        return max(floor_pct, TARGET_MARGIN_PCT)
    return max(LIST_MARGIN_PCT, TARGET_MARGIN_PCT)


def build_branded_variations(floor_pct: float | None = None) -> list[BrandedVariant]:
    """Every sellable branded variant (product x size x colour), each priced to
    clear the 60% net-margin floor. Variants the Gelato sync has discontinued are
    dropped, exactly like a discontinued frame."""
    from quoteforge.etsy.variations import min_price_for_margin, net_margin_pct
    floor = _list_floor(floor_pct)
    out: list[BrandedVariant] = []
    for p in BRANDED_CATALOG:
        for size in p.sizes:
            for color in p.colors:
                sku = _variant_sku(p, size, color)
                cost = _variant_cost(p, sku)
                if cost is None:
                    continue
                price = min_price_for_margin(cost, floor)
                out.append(BrandedVariant(
                    product_id=p.product_id, name=p.name, size=size, color=color,
                    gelato_sku=sku, gelato_cost=cost, price=price,
                    margin_pct=net_margin_pct(price, cost), placement=p.placement))
    return out


def branded_skus() -> list[str]:
    """Every branded variant SKU (the fulfillment routing keys), sorted."""
    return sorted({_variant_sku(p, s, c)
                   for p in BRANDED_CATALOG for s in p.sizes for c in p.colors})


# ── Fulfilment resolver: storefront cart line -> variant SKU ──────
# Mirrors apparel_catalog.py's ingest seam. The storefront records a branded
# choice as a format ("{product} - {colour}") plus a size; order-ingest calls
# these pure functions to turn that basket line into the variant SKU, which maps
# to a real Gelato UID via the SAME map mechanism wall-art and apparel SKUs use.
# Pure + side-effect-free, so safe to call from any ingest path.

def parse_branded_format(fmt: str) -> tuple[str | None, str | None]:
    """('Organic Cotton Tote Bag - Natural') -> (product_id, colour); (None, None)
    for anything that is not a real branded format (so apparel/wall-art are safe)."""
    if not fmt or " - " not in fmt:
        return (None, None)
    name, _, color = fmt.partition(" - ")
    p = next((x for x in BRANDED_CATALOG if x.name == name.strip()), None)
    return (p.product_id, color.strip()) if p else (None, None)


def branded_sku_for(product_id: str, size: str, color: str) -> str | None:
    """The variant SKU for a (product, size, colour), or None if the combination
    is not in the catalogue (so a bad size/colour can never route to production)."""
    p = get_product(product_id)
    if not p or not branded_sellable(product_id) \
            or size not in p.sizes or color not in p.colors:
        return None    # not-sellable (e.g. phonecase) never resolves a routing SKU
    return _variant_sku(p, size, color)


def resolve_branded_sku(fmt: str, size: str) -> str | None:
    """Storefront basket line ("Organic Cotton Tote Bag - Natural", "One Size") ->
    variant SKU, or None when the line is not a valid branded selection. The single
    entry point order-ingest calls to obtain a fulfilment routing key; None means
    'not branded / not orderable' so the caller routes to manual review."""
    pid, color = parse_branded_format(fmt)
    if not pid:
        return None
    return branded_sku_for(pid, size, color)


def enrich_branded_order(order_data: dict) -> dict:
    """Merge branded fields into an order. {} for non-branded orders. Single ingest seam."""
    fmt = (order_data.get("material") or order_data.get("fmt")
           or order_data.get("product_format") or order_data.get("format") or "")
    size = (order_data.get("product_size") or order_data.get("size") or "")
    pid, color = parse_branded_format(fmt)
    if not pid:
        return {}
    sku = branded_sku_for(pid, size, color)
    out: dict = {"product_type": "branded", "product_id": pid,
                 "color": color, "material": fmt, "gelato_sku": sku}
    p = get_product(pid)
    if p and sku:
        cost = _variant_cost(p, sku)
        if cost is not None:
            out["gelato_cost"] = cost
    from quoteforge.automation.gelato_variant_resolver import resolve_variant_uid
    uid = resolve_variant_uid(sku, pid, color, size)
    if uid:
        out["gelato_product_uid"] = uid
    return out


# ── Isolated Gelato placeholder guard (separate from print + apparel guards) ──

def verify_branded_mappings() -> dict:
    """Every branded variant GO-LIVE READY when its UID is statically mapped OR its
    family is mapped (resolved dynamically). Independent of the print + apparel guards."""
    from quoteforge.automation.gelato_sync import _uid_map
    from quoteforge.automation.gelato_variant_resolver import family_covered
    uid_map = _uid_map()
    vs = build_branded_variations()
    placeholders = []
    model_gaps = []
    for v in vs:
        # Phone cases are MODEL-SPECIFIC on the print partner (one UID = one phone
        # model). A generic iPhone/Samsung family UID cannot fulfil a real order, so
        # phonecase is never go-live-ready until per-model UIDs + a model-capture
        # field exist - regardless of family coverage.
        if str(v.product_id).startswith("phonecase"):
            model_gaps.append(v.gelato_sku)
            placeholders.append(v.gelato_sku)
            continue
        st = uid_map.get(v.gelato_sku)
        if st and not str(st).upper().startswith("GEL-"):
            continue
        if family_covered(v.product_id):
            continue
        placeholders.append(v.gelato_sku)
    total = len(vs)
    return {"total": total, "configured": total - len(placeholders),
            "placeholder_count": len(placeholders), "placeholders": placeholders,
            "model_specific_gaps": model_gaps,
            "all_real": not placeholders}
