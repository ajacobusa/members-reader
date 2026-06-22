"""Custom Calendars family (Gelato-fulfilled).

A self-contained parallel module modeled on mug_catalog.py. Calendars differ from
mugs only in shape:
  * each calendar type is one listing with its own print bound
    (calendar_dimensions_for), sized to a PORTRAIT white-paper cover field printed
    dark-on-white like a mug body.
  * variants are (paper-size x paper-colour); a calendar's "colour" is the paper
    stock, while the design prints on the white cover.
  * CalendarProduct adds pages (the number of leaves, 12 months + cover = 13) and
    binding (how the leaves are bound, e.g. coil / wire-o).
Costs are seeded (modeled) and overridden live by the Gelato sync; pricing always
re-derives from current cost to hold the 60% net-margin floor. Seed SKUs ship as
GEL-* placeholders mapped to real Gelato UIDs before go-live (verify_calendar_mappings).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CAL_DIMS: tuple[int, int] = (2480, 3508)


@dataclass
class CalendarProduct:
    """One sellable calendar product line with its paper sizes, paper colours,
    print geometry, seed cost and recommended Gelato blank.

    Calendars add pages (the number of leaves: 12 months + a cover = 13) and
    binding (how the leaves are bound to the spine, e.g. coil or wire-o)."""
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
    width_px: int = DEFAULT_CAL_DIMS[0]
    height_px: int = DEFAULT_CAL_DIMS[1]
    placement: str = "front"
    pages: int = 13
    binding: str = "coil"


_CAL_TYPES = [
    ("wall_cal", "Wall Calendar", "Wall Calendar", "Wall Calendars",
     ["A3", "A4"], ["White"], 9.0, "Gelato Wall Calendar", "Premium", 2480, 3508, 13, "coil"),
    ("desk_cal", "Desk Calendar", "Desk Calendar", "Desk Calendars",
     ["A5"], ["White"], 7.0, "Gelato Desk Calendar", "Classic", 2480, 1748, 13, "wire-o"),
    ("family_cal", "Family Organizer Calendar", "Family Calendar", "Family Calendars",
     ["A3"], ["White"], 10.0, "Gelato Family Calendar", "Premium", 2480, 3508, 13, "coil"),
    ("corporate_cal", "Corporate Branded Calendar", "Corporate Calendar", "Corporate Calendars",
     ["A3", "A4"], ["White"], 10.0, "Gelato Corporate Calendar", "Premium", 2480, 3508, 13, "coil"),
    ("photo_cal", "Photo Calendar", "Photo Calendar", "Photo Calendars",
     ["A4"], ["White"], 8.0, "Gelato Photo Calendar", "Classic", 2480, 3508, 13, "coil"),
    ("event_cal", "Event & Countdown Calendar", "Event Calendar", "Event Calendars",
     ["A6"], ["White"], 6.0, "Gelato Event Calendar", "Classic", 1748, 2480, 13, "wire-o"),
    ("promo_cal", "Business Promotional Calendar", "Promotional Calendar", "Business-Promotional Calendars",
     ["A4"], ["White"], 8.0, "Gelato Promo Calendar", "Classic", 2480, 3508, 13, "coil"),
]


def _build_catalog() -> list[CalendarProduct]:
    """Build the calendar product catalog from the type spec, one line per type."""
    out: list[CalendarProduct] = []
    for pid, name, type_name, cat, sizes, colors, cost, brand, tier, w, h, pages, binding in _CAL_TYPES:
        out.append(CalendarProduct(
            product_id=pid, name=name, type_name=type_name, category=cat,
            sizes=list(sizes), colors=list(colors), base_cost=cost,
            sku_prefix=f"GEL-{pid.upper()}", brand=brand, tier=tier,
            width_px=w, height_px=h, pages=pages, binding=binding))
    return out


CALENDAR_CATALOG: list[CalendarProduct] = _build_catalog()


@dataclass
class CalendarVariant:
    """One sellable calendar product/paper-size/paper-colour combination with cost and floor price."""
    product_id: str
    name: str
    size: str
    color: str
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    placement: str = "front"


def get_calendar(product_id: str) -> CalendarProduct | None:
    """Find a calendar product by id (case-insensitive), or None."""
    key = (product_id or "").strip().lower()
    return next((p for p in CALENDAR_CATALOG if p.product_id == key), None)


def calendar_dimensions_for(product_id: str) -> tuple[int, int]:
    """(width_px, height_px) of the print area for a calendar, or a safe default.

    The design editor reads this to bound calendar art to the printable portrait
    cover field instead of the full poster canvas."""
    p = get_calendar(product_id)
    return (p.width_px, p.height_px) if p else DEFAULT_CAL_DIMS


def _variant_sku(p: CalendarProduct, size: str, color: str) -> str:
    """Stable per-variant SKU, e.g. GEL-WALL_CAL-A3-WHITE."""
    part = lambda s: s.upper().replace(" ", "-")
    return f"{p.sku_prefix}-{part(size)}-{part(color)}"


def _variant_cost(p: CalendarProduct, sku: str) -> float | None:
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
    """The calendar anchor margin: the LIST target, never below the 60% floor.
    The global TARGET_MARGIN_PCT is an ABSOLUTE floor even if a lower override is
    passed, mirroring the apparel + branded + print + mug variations."""
    from quoteforge.config import LIST_MARGIN_PCT, TARGET_MARGIN_PCT
    if floor_pct is not None:
        return max(floor_pct, TARGET_MARGIN_PCT)
    return max(LIST_MARGIN_PCT, TARGET_MARGIN_PCT)


def build_calendar_variations(floor_pct: float | None = None) -> list[CalendarVariant]:
    """Every sellable calendar variant (product x paper-size x paper-colour), each
    priced to clear the 60% net-margin floor. Variants the Gelato sync has
    discontinued are dropped, exactly like a discontinued frame."""
    from quoteforge.etsy.variations import min_price_for_margin, net_margin_pct
    floor = _list_floor(floor_pct)
    out: list[CalendarVariant] = []
    for p in CALENDAR_CATALOG:
        for size in p.sizes:
            for color in p.colors:
                sku = _variant_sku(p, size, color)
                cost = _variant_cost(p, sku)
                if cost is None:
                    continue
                price = min_price_for_margin(cost, floor)
                out.append(CalendarVariant(
                    product_id=p.product_id, name=p.name, size=size, color=color,
                    gelato_sku=sku, gelato_cost=cost, price=price,
                    margin_pct=net_margin_pct(price, cost), placement=p.placement))
    return out


def calendar_skus() -> list[str]:
    """Every calendar variant SKU (the fulfillment routing keys), sorted."""
    return sorted({_variant_sku(p, s, c)
                   for p in CALENDAR_CATALOG for s in p.sizes for c in p.colors})


# ── Fulfilment resolver: storefront cart line -> variant SKU ──────
# Mirrors mug_catalog.py's ingest seam. The storefront records a calendar
# choice as a format ("{product} - {colour}") plus a size; order-ingest calls
# these pure functions to turn that basket line into the variant SKU, which maps
# to a real Gelato UID via the SAME map mechanism wall-art and mug SKUs use.
# Pure + side-effect-free, so safe to call from any ingest path.

def parse_calendar_format(fmt: str) -> tuple[str | None, str | None]:
    """('Wall Calendar - White') -> (product_id, colour); (None, None) for anything
    that is not a real calendar format (so apparel/branded/mug/wall-art are safe)."""
    if not fmt or " - " not in fmt:
        return (None, None)
    name, _, color = fmt.partition(" - ")
    p = next((x for x in CALENDAR_CATALOG if x.name == name.strip()), None)
    return (p.product_id, color.strip()) if p else (None, None)


def calendar_sku_for(product_id: str, size: str, color: str) -> str | None:
    """The variant SKU for a (product, size, colour), or None if the combination
    is not in the catalogue (so a bad size/colour can never route to production)."""
    p = get_calendar(product_id)
    if not p or size not in p.sizes or color not in p.colors:
        return None
    return _variant_sku(p, size, color)


def resolve_calendar_sku(fmt: str, size: str) -> str | None:
    """Storefront basket line ("Wall Calendar - White", "A3") -> variant SKU, or
    None when the line is not a valid calendar selection. The single entry point
    order-ingest calls to obtain a fulfilment routing key; None means 'not calendar
    / not orderable' so the caller routes to manual review."""
    pid, color = parse_calendar_format(fmt)
    if not pid:
        return None
    return calendar_sku_for(pid, size, color)


def enrich_calendar_order(order_data: dict) -> dict:
    """Merge calendar fields into an order. {} for non-calendar orders. Single ingest seam."""
    fmt = (order_data.get("material") or order_data.get("fmt")
           or order_data.get("product_format") or order_data.get("format") or "")
    size = (order_data.get("product_size") or order_data.get("size") or "")
    pid, color = parse_calendar_format(fmt)
    if not pid:
        return {}
    sku = calendar_sku_for(pid, size, color)
    out: dict = {"product_type": "calendar", "product_id": pid,
                 "color": color, "material": fmt, "gelato_sku": sku}
    p = get_calendar(pid)
    if p and sku:
        cost = _variant_cost(p, sku)
        if cost is not None:
            out["gelato_cost"] = cost
    from quoteforge.automation.gelato_variant_resolver import resolve_variant_uid
    uid = resolve_variant_uid(sku, pid, color, size)
    if uid:
        out["gelato_product_uid"] = uid
    return out


# ── Isolated Gelato placeholder guard (separate from print + apparel + branded + mug guards) ──

def verify_calendar_mappings() -> dict:
    """Every calendar variant GO-LIVE READY when its UID is statically mapped OR its
    family is mapped (resolved dynamically). Independent of the print + apparel +
    branded + mug guards."""
    from quoteforge.automation.gelato_sync import _uid_map
    from quoteforge.automation.gelato_variant_resolver import family_covered
    uid_map = _uid_map()
    vs = build_calendar_variations()
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
