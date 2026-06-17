"""Apparel product family — T-Shirt, Hoodie, Sweatshirt (Gelato-fulfilled).

This is a SELF-CONTAINED parallel module that sits alongside the working
poster/frame catalog and never modifies it. Apparel differs from wall art in
three ways that this module owns end to end:

  1. Variants are (size x colour), not a single fixed SKU. The existing print
     listing spends both Etsy variation axes on Size + Format, so apparel CANNOT
     share that path - each garment becomes its own listing (Size + Colour).
  2. The print area is a garment chest, NOT a 5400x7200 poster. The customer
     design editor reads `apparel_dimensions_for()` to draw the print-safe
     boundary so art is never silently cropped.
  3. It carries its OWN Gelato placeholder guard (`verify_apparel_mappings`) so
     the print catalog's guard - which existing go-live tests pin - is untouched.

Costs are seeded to match the strategic catalog in `product_lines.py`
(T-Shirt 13 / Hoodie 28 / Sweatshirt 24) and are overridden live by the Gelato
sync via `catalog_state`, exactly like frames. Pricing always re-derives from the
current cost to hold the 60% net-margin floor.

Seed SKUs ship as GEL-* placeholders; each must be mapped to a real Gelato
product UID (in GELATO_UID_MAP) before go-live, or `verify_apparel_mappings()`
flags it loudly.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Apparel front-chest print area at 300 DPI (~12x16 in / 30x40 cm). Modeled until
# confirmed against the live Gelato product spec; per-garment overridable below.
DEFAULT_APPAREL_DIMS: tuple[int, int] = (3600, 4800)

# Extended sizes cost more to fulfill; modeled upcharge added to the base cost.
SIZE_UPCHARGE: dict[str, float] = {"2XL": 2.0, "3XL": 4.0}


@dataclass
class ApparelGarment:
    """One garment line: its sizes, colours, print geometry and base cost."""
    garment_id: str            # "tshirt" | "hoodie" | "sweatshirt"
    name: str                  # must match product_lines.py exactly
    sizes: list[str]
    colors: list[str]
    base_cost: float           # Gelato cost for the base size (USD)
    sku_prefix: str            # "GEL-TSHIRT" -> variant SKUs derive from this
    width_px: int = DEFAULT_APPAREL_DIMS[0]
    height_px: int = DEFAULT_APPAREL_DIMS[1]
    category: str = "apparel"
    placement: str = "front"   # launch = front only (back/pocket are future)


# The launch apparel range. Colours are realistic Gelato garment colours; costs
# mirror product_lines.py so the strategic catalog and the live catalog agree.
APPAREL_CATALOG: list[ApparelGarment] = [
    ApparelGarment(
        garment_id="tshirt", name="T-Shirt",
        sizes=["S", "M", "L", "XL", "2XL"],
        colors=["Black", "White", "Navy", "Heather Grey", "Sand"],
        base_cost=13.00, sku_prefix="GEL-TSHIRT"),
    ApparelGarment(
        garment_id="hoodie", name="Hoodie",
        sizes=["S", "M", "L", "XL", "2XL"],
        colors=["Black", "Heather Grey", "Navy", "Maroon", "White"],
        base_cost=28.00, sku_prefix="GEL-HOODIE"),
    ApparelGarment(
        garment_id="sweatshirt", name="Sweatshirt",
        sizes=["S", "M", "L", "XL", "2XL"],
        colors=["Black", "Heather Grey", "Navy", "Sand", "White"],
        base_cost=24.00, sku_prefix="GEL-SWEATSHIRT"),
]


@dataclass
class ApparelVariant:
    """One sellable garment/size/colour combination with cost and floor price."""
    garment_id: str
    name: str
    size: str
    color: str
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    placement: str = "front"


# ── Lookups ──────────────────────────────────────────────────────

def get_garment(garment_id: str) -> ApparelGarment | None:
    """Find a garment by id (case-insensitive), or None."""
    key = (garment_id or "").strip().lower()
    return next((g for g in APPAREL_CATALOG if g.garment_id == key), None)


def apparel_dimensions_for(garment_id: str) -> tuple[int, int]:
    """(width_px, height_px) of the print area for a garment, or a safe default.

    The design editor reads this to bound apparel art to the printable chest
    region instead of the full poster canvas."""
    g = get_garment(garment_id)
    return (g.width_px, g.height_px) if g else DEFAULT_APPAREL_DIMS


def _variant_sku(g: ApparelGarment, size: str, color: str) -> str:
    """Stable per-variant SKU, e.g. GEL-TSHIRT-2XL-HEATHER-GREY."""
    part = lambda s: s.upper().replace(" ", "-")
    return f"{g.sku_prefix}-{part(size)}-{part(color)}"


def _variant_cost(g: ApparelGarment, size: str, sku: str) -> float | None:
    """Base cost + extended-size upcharge, with any live Gelato override applied.

    Returns None when the live sync has marked the variant discontinued."""
    from quoteforge.etsy.catalog_state import sku_override
    ov = sku_override(sku)
    if ov and ov.get("available") is False:
        return None
    base = g.base_cost + SIZE_UPCHARGE.get(size, 0.0)
    if ov and ov.get("cost") is not None:
        return round(ov["cost"], 2)
    return round(base, 2)


def _list_floor(floor_pct: float | None) -> float:
    """The apparel anchor margin: the LIST target, never below the 60% floor.
    Mirrors how the print variations anchor and discount toward the floor - the
    global TARGET_MARGIN_PCT is an ABSOLUTE floor even if a lower override is
    passed (see variations.floor_for_tier for the same guarantee)."""
    from quoteforge.config import LIST_MARGIN_PCT, TARGET_MARGIN_PCT
    if floor_pct is not None:
        return max(floor_pct, TARGET_MARGIN_PCT)
    return max(LIST_MARGIN_PCT, TARGET_MARGIN_PCT)


# ── Variants + pricing (reuses the print module's floor math) ─────

def build_apparel_variations(floor_pct: float | None = None) -> list[ApparelVariant]:
    """Every sellable apparel variant (garment x size x colour), each priced to
    clear the 60% net-margin floor. Variants the Gelato sync has discontinued are
    dropped, exactly like a discontinued frame."""
    from quoteforge.etsy.variations import min_price_for_margin, net_margin_pct
    floor = _list_floor(floor_pct)
    out: list[ApparelVariant] = []
    for g in APPAREL_CATALOG:
        for size in g.sizes:
            for color in g.colors:
                sku = _variant_sku(g, size, color)
                cost = _variant_cost(g, size, sku)
                if cost is None:
                    continue                       # discontinued -> drop
                price = min_price_for_margin(cost, floor)
                out.append(ApparelVariant(
                    garment_id=g.garment_id, name=g.name, size=size, color=color,
                    gelato_sku=sku, gelato_cost=cost, price=price,
                    margin_pct=net_margin_pct(price, cost),
                    placement=g.placement))
    return out


def apparel_skus() -> list[str]:
    """Every apparel variant SKU (the fulfillment routing keys), sorted."""
    skus = {_variant_sku(g, s, c)
            for g in APPAREL_CATALOG for s in g.sizes for c in g.colors}
    return sorted(skus)


# ── Fulfilment resolver: storefront cart line -> variant SKU ──────
# The storefront records an apparel choice as CURFMT = "{garment} - {colour}"
# plus a size. Order-ingest calls these pure functions to turn that basket line
# into the variant SKU, which maps to a real Gelato apparel UID via the SAME
# GELATO_UID_MAP mechanism wall-art SKUs use. Pure + side-effect-free so they are
# safe to call from any ingest path without touching the live order pipeline.

def parse_apparel_format(fmt: str) -> tuple[str | None, str | None]:
    """Split a storefront apparel format ("T-Shirt - Black") into
    (garment_id, colour). Returns (None, None) for anything that is not a real
    apparel format - so a wall-art format like "Framed - Oak" is never misread
    as apparel."""
    if not fmt or " - " not in fmt:
        return (None, None)
    name, _, color = fmt.partition(" - ")
    g = next((x for x in APPAREL_CATALOG if x.name == name.strip()), None)
    if not g:
        return (None, None)
    return (g.garment_id, color.strip())


def apparel_sku_for(garment_id: str, size: str, color: str) -> str | None:
    """The variant SKU for a (garment, size, colour), or None if the combination
    is not in the catalogue (so a bad size/colour can never route to production)."""
    g = get_garment(garment_id)
    if not g or size not in g.sizes or color not in g.colors:
        return None
    return _variant_sku(g, size, color)


def resolve_apparel_sku(fmt: str, size: str) -> str | None:
    """Storefront basket line ("T-Shirt - Black", "M") -> variant SKU, or None
    when the line is not a valid apparel selection. The single entry point
    order-ingest will call to obtain a fulfilment routing key for an apparel
    item; None means 'not apparel / not orderable' - the caller routes to manual
    review rather than guessing."""
    gid, color = parse_apparel_format(fmt)
    if not gid:
        return None
    return apparel_sku_for(gid, size, color)


def resolve_apparel_uid(sku: str | None) -> str | None:
    """Map an apparel variant SKU to its REAL Gelato product UID via the
    GELATO_UID_MAP env (the SAME mechanism wall-art SKUs use). Returns None when
    the SKU is unmapped or still a GEL-* placeholder, so the caller routes to
    manual review instead of submitting a placeholder to production."""
    if not sku:
        return None
    from quoteforge.automation.gelato_sync import _uid_map
    uid = _uid_map().get(sku)
    if not uid or str(uid).upper().startswith("GEL-"):
        return None
    return uid


def enrich_apparel_order(order_data: dict) -> dict:
    """Given an order carrying an apparel format ("T-Shirt - Black") + size,
    return the apparel fields to MERGE into the order: product_type, garment_id,
    color, gelato_sku, and gelato_product_uid (the real UID, omitted when the SKU
    is unmapped so routing falls back to manual). Returns {} for a non-apparel
    order so wall-art orders are completely unaffected.

    This is the single ingest seam: call it once where order_data is assembled."""
    fmt = (order_data.get("material") or order_data.get("fmt")
           or order_data.get("product_format") or order_data.get("format") or "")
    size = (order_data.get("product_size") or order_data.get("size") or "")
    gid, color = parse_apparel_format(fmt)
    if not gid:
        return {}
    sku = apparel_sku_for(gid, size, color)
    out: dict = {"product_type": "apparel", "garment_id": gid,
                 "color": color, "material": fmt, "gelato_sku": sku}
    # Persist the TRUE garment cost (base + size upcharge + any live override) so
    # every downstream financial/margin module reads an accurate apparel cost
    # straight off the order - no per-module apparel special-casing needed.
    g = get_garment(gid)
    if g and sku:
        cost = _variant_cost(g, size, sku)
        if cost is not None:
            out["gelato_cost"] = cost
    uid = resolve_apparel_uid(sku)
    if uid:
        out["gelato_product_uid"] = uid
    return out


# ── Isolated Gelato placeholder guard (separate from the print guard) ──

def verify_apparel_mappings() -> dict:
    """Check every apparel variant SKU carries a REAL Gelato UID (not a GEL-*
    seed placeholder). Independent of `gelato_catalog.verify_catalog_mappings`
    so the print go-live guard stays byte-for-byte unchanged."""
    skus = apparel_skus()
    placeholders = [s for s in skus if not s or s.upper().startswith("GEL-")]
    total = len(skus)
    return {
        "total": total,
        "configured": total - len(placeholders),
        "placeholder_count": len(placeholders),
        "placeholders": placeholders,
        "all_real": not placeholders,
    }
