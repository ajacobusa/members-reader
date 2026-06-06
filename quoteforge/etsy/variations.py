"""Etsy product variations + 60%-floor pricing for one-listing-many-options.

Each design is sold as ONE Etsy listing with variations across Material, Size,
and (for framed) Frame color. Every variation is priced to clear the 60% net
margin floor after Gelato cost + Etsy fees; tiers below the floor are dropped.

Fulfillment reality (Gelato):
  - Poster  : ships UNFRAMED.
  - Framed  : real wood frame; choice is FRAME COLOR (Black/White/Natural Oak).
  - Canvas  : gallery-wrapped = the "open" canvas option (no external frame).
  - Acrylic/Metal : frameless by design.

The upsell ladder is by MATERIAL (Gelato has no good/better/best frame ladder):
  entry = Poster  ->  mid = Framed  ->  top = Canvas / Acrylic / Metal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from quoteforge.config import TARGET_MARGIN_PCT

ETSY_FEE_PCT = 0.065          # Etsy transaction + payment processing (approx)
ETSY_LISTING_FEE = 0.20       # per-sale listing cost
FRAME_COLORS = ["Black", "White", "Natural Oak"]

# How each material is presented + whether a frame applies.
MATERIAL_LABELS = {
    "poster": "Poster (unframed print)",
    "framed": "Framed print (wood frame)",
    "canvas": "Canvas (gallery-wrapped / open)",
    "acrylic": "Acrylic (frameless)",
    "metal": "Metal (frameless)",
}
# Upsell tier per material.
TIER = {"poster": "entry", "framed": "mid",
        "canvas": "top", "acrylic": "top", "metal": "top"}


@dataclass
class Variation:
    material: str
    size: str
    frame_color: str          # "" when not applicable
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    tier: str


def min_price_for_margin(cost: float, floor_pct: int = None,
                         fee: float = ETSY_FEE_PCT,
                         listing_fee: float = ETSY_LISTING_FEE) -> float:
    """Smallest .99-ending price whose NET margin >= floor.

    margin = (price - cost - price*fee - listing_fee) / price >= floor
    => price >= (cost + listing_fee) / (1 - fee - floor)
    """
    floor = (floor_pct if floor_pct is not None else TARGET_MARGIN_PCT) / 100.0
    denom = 1.0 - fee - floor
    if denom <= 0:
        raise ValueError("fee + floor must be < 1")
    raw = (cost + listing_fee) / denom
    return round(math.ceil(raw) - 0.01, 2)   # next whole dollar, minus 1c => x.99


def net_margin_pct(price: float, cost: float, fee: float = ETSY_FEE_PCT,
                   listing_fee: float = ETSY_LISTING_FEE) -> int:
    profit = price - cost - price * fee - listing_fee
    return round(profit / price * 100) if price else 0


def build_variations(floor_pct: int = None) -> list[Variation]:
    """All sellable variations across the catalog, each priced at the 60% floor.
    Framed expands into one row per frame color (same price)."""
    from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
    out: list[Variation] = []
    for p in GELATO_CATALOG:
        if p.category not in MATERIAL_LABELS:    # skip mugs / unknowns
            continue
        price = min_price_for_margin(p.gelato_cost_usd, floor_pct)
        margin = net_margin_pct(price, p.gelato_cost_usd)
        colors = FRAME_COLORS if p.category == "framed" else [""]
        for color in colors:
            out.append(Variation(
                material=p.category, size=p.size, frame_color=color,
                gelato_sku=p.gelato_sku, gelato_cost=p.gelato_cost_usd,
                price=price, margin_pct=margin, tier=TIER[p.category]))
    return out


def price_range(floor_pct: int = None) -> tuple[float, float]:
    prices = [v.price for v in build_variations(floor_pct)]
    return (min(prices), max(prices)) if prices else (0.0, 0.0)


def materials_offered() -> list[str]:
    """Distinct material labels present in the catalog, in upsell order."""
    from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
    order = ["poster", "framed", "canvas", "acrylic", "metal"]
    present = {p.category for p in GELATO_CATALOG}
    return [MATERIAL_LABELS[m] for m in order if m in present]


def options_block() -> str:
    """Human-readable 'choose your product' block for the listing description,
    grouped by material with sizes, frame colors, and the entry price each."""
    vs = build_variations()
    by_mat: dict[str, list[Variation]] = {}
    for v in vs:
        by_mat.setdefault(v.material, []).append(v)
    order = ["poster", "framed", "canvas", "acrylic", "metal"]
    lines = ["CHOOSE YOUR PRODUCT (select Material + Size at checkout)"]
    for mat in order:
        rows = by_mat.get(mat)
        if not rows:
            continue
        sizes = sorted({r.size.replace(" in", "") for r in rows})
        low = min(r.price for r in rows)
        extra = (f" - frame color: {', '.join(FRAME_COLORS)}"
                 if mat == "framed" else "")
        lines.append(f"- {MATERIAL_LABELS[mat]}: {', '.join(sizes)} "
                     f"(from ${low:.2f}){extra}")
    lines.append("Canvas is gallery-wrapped (\"open\") - ready to hang as-is.")
    return "\n".join(lines)


def upsell_ladder() -> dict[str, float]:
    """Lowest price at each tier — used for cross-sell/upsell messaging."""
    vs = build_variations()
    out: dict[str, float] = {}
    for v in vs:
        if v.tier not in out or v.price < out[v.tier]:
            out[v.tier] = v.price
    return out
