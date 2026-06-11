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


def floor_for_tier(tier: str) -> float:
    """The configured net-margin floor for an upsell tier (never below target)."""
    from quoteforge.config import (
        MARGIN_FLOOR_ENTRY, MARGIN_FLOOR_MID, MARGIN_FLOOR_TOP, TARGET_MARGIN_PCT)
    floor = {"entry": MARGIN_FLOOR_ENTRY, "mid": MARGIN_FLOOR_MID,
             "top": MARGIN_FLOOR_TOP}.get(tier, TARGET_MARGIN_PCT)
    return max(floor, TARGET_MARGIN_PCT)   # global 60% is an absolute floor


def list_floor_for_tier(tier: str) -> float:
    """The LIST (anchor) margin for single-item pricing - the higher of the list
    target and the tier floor. Bundles discount from here down to floor_for_tier."""
    from quoteforge.config import LIST_MARGIN_PCT
    return max(LIST_MARGIN_PCT, floor_for_tier(tier))


# Quantity-discount ladder: (min qty, target discount). Discounts are CAPPED so
# the unit price never drops below the 60% net floor.
QTY_DISCOUNT = [(4, 0.15), (3, 0.12), (2, 0.08), (1, 0.0)]


def tier_discount(qty: int) -> float:
    """Bundle discount for a quantity (largest threshold <= qty wins)."""
    for threshold, disc in QTY_DISCOUNT:
        if qty >= threshold:
            return disc
    return 0.0


def floor_price(cost: float, tier: str = "entry") -> float:
    """Lowest price that still clears the tier's net-margin floor (60%)."""
    return min_price_for_margin(cost, floor_for_tier(tier))


def bundle_quote(list_price: float, cost: float, qty: int,
                 tier: str = "entry") -> dict:
    """Per-unit + total price for `qty`, applying the quantity discount but never
    breaking the 60% floor. Returns the effective discount, savings and margin."""
    target = tier_discount(qty)
    fp = floor_price(cost, tier)
    unit = max(round(list_price * (1 - target), 2), fp)   # cap at the floor
    eff = round((list_price - unit) / list_price * 100) if list_price else 0
    total = round(unit * qty, 2)
    return {
        "qty": qty, "unit": unit, "total": total,
        "list_total": round(list_price * qty, 2),
        "savings": round((list_price - unit) * qty, 2),
        "discount_pct": eff, "margin_pct": net_margin_pct(unit, cost),
        "holds_floor": net_margin_pct(unit, cost) >= floor_for_tier(tier),
    }


def bundle_table(list_price: float, cost: float, tier: str = "entry") -> list[dict]:
    """Quote rows for 1-4 units (the 'buy more, save more' ladder)."""
    return [bundle_quote(list_price, cost, q, tier) for q in (1, 2, 3, 4)]


@dataclass
class Variation:
    material: str
    size: str
    frame_color: str          # frame NAME for framed, else ""
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    tier: str
    frame_tier: str = ""      # "high"|"mid"|"low" for framed, else ""


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
    """Net margin %% after Gelato cost + marketplace fee + listing fee."""
    profit = price - cost - price * fee - listing_fee
    return round(profit / price * 100) if price else 0


def _live_cost(sku: str, base: float) -> float:
    """Base Gelato cost with any live override from the sync applied."""
    from quoteforge.etsy.catalog_state import sku_override
    ov = sku_override(sku)
    return ov.get("cost", base) if ov else base


def build_variations(floor_pct: int = None) -> list[Variation]:
    """All sellable variations, each priced at the 60% floor.

    - Poster / Canvas / Acrylic / Metal come from the catalog (costs may be
      live-overridden by the Gelato sync; unavailable SKUs are dropped).
    - Framed expands into Poster size × AVAILABLE frame (6-tier ladder); a
      framed variation's cost = base print cost + the frame's upcharge.
    """
    from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
    from quoteforge.etsy.catalog_state import sku_override
    from quoteforge.etsy.frames import available_frames
    out: list[Variation] = []

    posters = {}
    for p in GELATO_CATALOG:
        if p.category == "poster":
            posters[p.size] = p
        if p.category not in MATERIAL_LABELS or p.category == "framed":
            continue
        ov = sku_override(p.gelato_sku)
        if ov and ov.get("available") is False:
            continue                              # discontinued -> drop
        cost = _live_cost(p.gelato_sku, p.gelato_cost_usd)
        tier = TIER[p.category]
        floor = floor_pct if floor_pct is not None else list_floor_for_tier(tier)
        price = min_price_for_margin(cost, floor)
        out.append(Variation(
            material=p.category, size=p.size, frame_color="",
            gelato_sku=p.gelato_sku, gelato_cost=cost,
            price=price, margin_pct=net_margin_pct(price, cost),
            tier=tier))

    # Framed = poster print + a chosen frame (only frames Gelato can fulfill).
    for size, p in posters.items():
        base = _live_cost(p.gelato_sku, p.gelato_cost_usd)
        for fr in available_frames():
            cost = round(base + fr.upcharge, 2)
            floor = floor_pct if floor_pct is not None else list_floor_for_tier("mid")
            price = min_price_for_margin(cost, floor)
            out.append(Variation(
                material="framed", size=size, frame_color=fr.name,
                gelato_sku=f"{p.gelato_sku}+{fr.gelato_sku}", gelato_cost=cost,
                price=price, margin_pct=net_margin_pct(price, cost),
                tier="mid", frame_tier=fr.tier))
    return out


def price_range(floor_pct: int = None) -> tuple[float, float]:
    """(lowest, highest) price across the full variations catalog."""
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
    grouped by material with sizes, frame tiers, and the entry price each."""
    from quoteforge.etsy.frames import frames_by_tier
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
        lines.append(f"- {MATERIAL_LABELS[mat]}: {', '.join(sizes)} "
                     f"(from ${low:.2f})")
    # Frame ladder (only what Gelato can currently fulfill).
    tiers = frames_by_tier()
    label = {"high": "Premium frames", "mid": "Classic frames", "low": "Essential frame"}
    frame_lines = []
    for t in ("high", "mid", "low"):
        names = [f.name for f in tiers.get(t, [])]
        if names:
            frame_lines.append(f"  - {label[t]}: {', '.join(names)}")
    if frame_lines:
        lines.append("Frame options (for the Framed material):")
        lines.extend(frame_lines)
    lines.append("Canvas is gallery-wrapped (\"open\") - ready to hang as-is.")
    # Buy-more-save-more ladder (from the quantity-discount tiers).
    tiers = sorted([(q, d) for q, d in QTY_DISCOUNT if d > 0])
    if tiers:
        parts = [f"{q}+ = {int(d*100)}% off" for q, d in tiers]
        lines.append("BUY MORE, SAVE MORE (gallery sets): " + ", ".join(parts)
                     + " - bundle a set for multiple rooms or gifts.")
    return "\n".join(lines)


def upsell_ladder() -> dict[str, float]:
    """Lowest price at each tier — used for cross-sell/upsell messaging."""
    vs = build_variations()
    out: dict[str, float] = {}
    for v in vs:
        if v.tier not in out or v.price < out[v.tier]:
            out[v.tier] = v.price
    return out
