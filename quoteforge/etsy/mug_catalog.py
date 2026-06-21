"""Custom Mugs family (Gelato-fulfilled).

A self-contained parallel module modeled on branded_catalog.py. Mugs differ from
branded merch only in shape:
  * each mug type is one listing with its own print bound (mug_dimensions_for),
    sized to a flat wrap panel printed on the white ceramic body.
  * variants are (capacity-size x accent-colour); a mug's "colour" is the
    handle/interior/rim accent, while the design prints on the white body.
  * MugProduct adds capacity_oz (the volume) and wraps (whether the art wraps the
    full body or is broken by the handle, e.g. accent/colour-interior/travel).
Costs are seeded (modeled) and overridden live by the Gelato sync; pricing always
re-derives from current cost to hold the 60% net-margin floor. Seed SKUs ship as
GEL-* placeholders mapped to real Gelato UIDs before go-live (verify_mug_mappings).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MUG_DIMS: tuple[int, int] = (2475, 1155)


@dataclass
class MugProduct:
    """One sellable mug product line with its capacities, accent colours, print
    geometry, seed cost and recommended Gelato blank.

    Mugs add capacity_oz (the drink volume) and wraps (True when the art wraps the
    full ceramic body, False when the handle breaks the wrap into a single panel)."""
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
    width_px: int = DEFAULT_MUG_DIMS[0]
    height_px: int = DEFAULT_MUG_DIMS[1]
    placement: str = "front"
    capacity_oz: int = 11
    wraps: bool = True


_MUG_TYPES = [
    ("classic_mug", "Classic Ceramic Mug (11oz)", "Coffee Mug", "Coffee Mugs",
     ["11oz"], ["White", "Black", "Navy", "Red", "Forest Green"],
     7.0, "Gelato Ceramic 11oz", "Value", 2475, 1155, 11, True),
    ("large_mug", "Large Ceramic Mug (15oz)", "Coffee Mug", "Ceramic Mugs",
     ["15oz"], ["White", "Black", "Navy"],
     8.0, "Gelato Ceramic 15oz", "Classic", 2790, 1320, 15, True),
    ("color_mug", "Colour-Interior Mug (11oz)", "Colour-Interior Mug", "Colour-Interior Mugs",
     ["11oz"], ["Black", "Navy", "Red", "Forest Green", "Royal Blue", "Maroon"],
     9.0, "Gelato Colour Mug", "Classic", 2200, 1155, 11, False),
    ("accent_mug", "Accent Mug", "Accent Mug", "Accent Mugs",
     ["11oz", "15oz"], ["Black", "Red", "Navy", "Dusty Rose", "Forest Green"],
     9.0, "Gelato Accent Mug", "Classic", 2200, 1155, 11, False),
    ("enamel_mug", "Enamel Camp Mug (12oz)", "Enamel Mug", "Enamel Mugs",
     ["12oz"], ["White", "Black", "Navy", "Red"],
     11.0, "Gelato Enamel 12oz", "Premium", 2400, 1050, 12, True),
    ("travel_mug", "Stainless Travel Mug (15oz)", "Travel Mug", "Travel Mugs",
     ["15oz"], ["White", "Silver", "Black"],
     13.0, "Gelato Travel 15oz", "Premium", 2600, 1700, 15, False),
    ("xl_mug", "Large-Capacity Mug (20oz)", "Large Mug", "Large-Capacity Mugs",
     ["20oz"], ["White", "Black", "Navy"],
     10.0, "Gelato Ceramic 20oz", "Premium", 3150, 1500, 20, True),
]


def _build_catalog() -> list[MugProduct]:
    """Build the mug product catalog from the type spec, one line per mug type."""
    out: list[MugProduct] = []
    for pid, name, type_name, cat, sizes, colors, cost, brand, tier, w, h, cap, wraps in _MUG_TYPES:
        out.append(MugProduct(
            product_id=pid, name=name, type_name=type_name, category=cat,
            sizes=list(sizes), colors=list(colors), base_cost=cost,
            sku_prefix=f"GEL-{pid.upper()}", brand=brand, tier=tier,
            width_px=w, height_px=h, capacity_oz=cap, wraps=wraps))
    return out


MUG_CATALOG: list[MugProduct] = _build_catalog()


@dataclass
class MugVariant:
    """One sellable mug product/capacity/accent-colour combination with cost and floor price."""
    product_id: str
    name: str
    size: str
    color: str
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    placement: str = "front"


def get_mug(product_id: str) -> MugProduct | None:
    """Find a mug product by id (case-insensitive), or None."""
    key = (product_id or "").strip().lower()
    return next((p for p in MUG_CATALOG if p.product_id == key), None)


def mug_dimensions_for(product_id: str) -> tuple[int, int]:
    """(width_px, height_px) of the print area for a mug, or a safe default.

    The design editor reads this to bound mug art to the printable wrap panel
    instead of the full poster canvas."""
    p = get_mug(product_id)
    return (p.width_px, p.height_px) if p else DEFAULT_MUG_DIMS


def _variant_sku(p: MugProduct, size: str, color: str) -> str:
    """Stable per-variant SKU, e.g. GEL-CLASSIC_MUG-11OZ-WHITE."""
    part = lambda s: s.upper().replace(" ", "-")
    return f"{p.sku_prefix}-{part(size)}-{part(color)}"


def _variant_cost(p: MugProduct, sku: str) -> float | None:
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
    """The mug anchor margin: the LIST target, never below the 60% floor.
    The global TARGET_MARGIN_PCT is an ABSOLUTE floor even if a lower override is
    passed, mirroring the apparel + branded + print variations."""
    from quoteforge.config import LIST_MARGIN_PCT, TARGET_MARGIN_PCT
    if floor_pct is not None:
        return max(floor_pct, TARGET_MARGIN_PCT)
    return max(LIST_MARGIN_PCT, TARGET_MARGIN_PCT)


def build_mug_variations(floor_pct: float | None = None) -> list[MugVariant]:
    """Every sellable mug variant (product x capacity x accent-colour), each priced
    to clear the 60% net-margin floor. Variants the Gelato sync has discontinued are
    dropped, exactly like a discontinued frame."""
    from quoteforge.etsy.variations import min_price_for_margin, net_margin_pct
    floor = _list_floor(floor_pct)
    out: list[MugVariant] = []
    for p in MUG_CATALOG:
        for size in p.sizes:
            for color in p.colors:
                sku = _variant_sku(p, size, color)
                cost = _variant_cost(p, sku)
                if cost is None:
                    continue
                price = min_price_for_margin(cost, floor)
                out.append(MugVariant(
                    product_id=p.product_id, name=p.name, size=size, color=color,
                    gelato_sku=sku, gelato_cost=cost, price=price,
                    margin_pct=net_margin_pct(price, cost), placement=p.placement))
    return out


def mug_skus() -> list[str]:
    """Every mug variant SKU (the fulfillment routing keys), sorted."""
    return sorted({_variant_sku(p, s, c)
                   for p in MUG_CATALOG for s in p.sizes for c in p.colors})


# ── Fulfilment resolver: storefront cart line -> variant SKU ──────
# Mirrors branded_catalog.py's ingest seam. The storefront records a mug
# choice as a format ("{product} - {colour}") plus a size; order-ingest calls
# these pure functions to turn that basket line into the variant SKU, which maps
# to a real Gelato UID via the SAME map mechanism wall-art and branded SKUs use.
# Pure + side-effect-free, so safe to call from any ingest path.

def parse_mug_format(fmt: str) -> tuple[str | None, str | None]:
    """('Classic Ceramic Mug (11oz) - White') -> (product_id, colour); (None, None)
    for anything that is not a real mug format (so apparel/branded/wall-art are safe)."""
    if not fmt or " - " not in fmt:
        return (None, None)
    name, _, color = fmt.partition(" - ")
    p = next((x for x in MUG_CATALOG if x.name == name.strip()), None)
    return (p.product_id, color.strip()) if p else (None, None)


def mug_sku_for(product_id: str, size: str, color: str) -> str | None:
    """The variant SKU for a (product, size, colour), or None if the combination
    is not in the catalogue (so a bad size/colour can never route to production)."""
    p = get_mug(product_id)
    if not p or size not in p.sizes or color not in p.colors:
        return None
    return _variant_sku(p, size, color)


def resolve_mug_sku(fmt: str, size: str) -> str | None:
    """Storefront basket line ("Classic Ceramic Mug (11oz) - White", "11oz") ->
    variant SKU, or None when the line is not a valid mug selection. The single
    entry point order-ingest calls to obtain a fulfilment routing key; None means
    'not mug / not orderable' so the caller routes to manual review."""
    pid, color = parse_mug_format(fmt)
    if not pid:
        return None
    return mug_sku_for(pid, size, color)


def enrich_mug_order(order_data: dict) -> dict:
    """Merge mug fields into an order. {} for non-mug orders. Single ingest seam."""
    fmt = (order_data.get("material") or order_data.get("fmt")
           or order_data.get("product_format") or order_data.get("format") or "")
    size = (order_data.get("product_size") or order_data.get("size") or "")
    pid, color = parse_mug_format(fmt)
    if not pid:
        return {}
    sku = mug_sku_for(pid, size, color)
    out: dict = {"product_type": "mug", "product_id": pid,
                 "color": color, "material": fmt, "gelato_sku": sku}
    p = get_mug(pid)
    if p and sku:
        cost = _variant_cost(p, sku)
        if cost is not None:
            out["gelato_cost"] = cost
    from quoteforge.automation.gelato_variant_resolver import resolve_variant_uid
    uid = resolve_variant_uid(sku, pid, color, size)
    if uid:
        out["gelato_product_uid"] = uid
    return out


# ── Isolated Gelato placeholder guard (separate from print + apparel + branded guards) ──

def verify_mug_mappings() -> dict:
    """Every mug variant GO-LIVE READY when its UID is statically mapped OR its
    family is mapped (resolved dynamically). Independent of the print + apparel +
    branded guards."""
    from quoteforge.automation.gelato_sync import _uid_map
    from quoteforge.automation.gelato_variant_resolver import family_covered
    uid_map = _uid_map()
    vs = build_mug_variations()
    placeholders = []
    for v in vs:
        st = uid_map.get(v.gelato_sku)
        if st and not str(st).upper().startswith("GEL-"):
            continue
        if family_covered(v.product_id):
            continue
        placeholders.append(v.gelato_sku)
    total = len(vs)
    return {"total": total, "configured": total - len(placeholders),
            "placeholder_count": len(placeholders), "placeholders": placeholders,
            "all_real": not placeholders}
