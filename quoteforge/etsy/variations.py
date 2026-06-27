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
from quoteforge.etsy.profit_calculator import (
    ETSY_TRANSACTION_FEE, ETSY_PAYMENT_FEE, ETSY_LISTING_FEE)

# ONE fee stack, shared with the profit ledger and margin guard: 6.5%
# transaction + 3% payment processing + $0.20 listing. (Was 6.5%-only here,
# which under-counted fees by 3% and made every "60% floor" actually clear
# ~57%.) LIST_MARGIN_PCT was retuned in tandem so live LIST prices are
# unchanged - only the bare floor (bundle caps / gallery sets) rises to a
# genuine 60%.
ETSY_FEE_PCT = ETSY_TRANSACTION_FEE + ETSY_PAYMENT_FEE   # 9.5% full stack

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


def line_subtotal(unit_price: float, qty: int, discount: float) -> float:
    """One basket line's subtotal: the discounted unit price (rounded to cents) times
    qty, rounded to cents - the SAME round-then-multiply order as the storefront
    _lineSub, so the Python canonical and the browser agree to the penny."""
    return round(round(unit_price * (1 - discount), 2) * int(qty), 2)


def basket_subtotal(lines: list) -> float:
    """Basket subtotal (the canonical Python source of the storefront cart math).

    The quantity discount keys off the TOTAL basket quantity - not per line - then each
    line's subtotal is summed. ``lines`` = [{"unit": float, "qty": int}, ...]. Mirrors
    _totalQty/qdisc/_lineSub/_cartTotal exactly.
    """
    total_qty = sum(int(l.get("qty", 1) or 1) for l in lines)
    d = tier_discount(total_qty)
    return round(sum(line_subtotal(float(l["unit"]), l.get("qty", 1) or 1, d)
                     for l in lines), 2)


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
    """One sellable material/size/frame combination with its cost and price."""
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


def _ns(s: str) -> str:
    """Normalise a size label for matching: lowercase, drop a trailing ' in'
    unit and all spaces, so '8x10 in', '8x10', and '8 x 10' all compare equal."""
    s = str(s or "").strip().lower()
    if s.endswith(" in"):
        s = s[:-3]
    return s.replace(" ", "")


def wallart_uid_for(material: str, size: str) -> "str | None":
    """Resolve an UNFRAMED wall-art order's Gelato productUid (the catalog
    gelato_sku) from material+size, so a poster/canvas/metal/acrylic order can
    auto-submit instead of being held as manual for a missing UID. FRAMED orders
    use a composite '{poster}+{frame}' SKU that is not a single Gelato productUid,
    so they return None (held for the operator) rather than risk an invalid submit."""
    if not material or not size:
        return None
    mat = str(material).lower()
    if "framed" in mat and "unframed" not in mat:   # 'unframed' contains 'framed'
        return None
    key = next((k for k in ("poster", "canvas", "acrylic", "metal")
                if k in mat), None)
    if key is None:
        return None
    try:
        for v in build_variations():
            if v.material == key and _ns(v.size) == _ns(size) and not v.frame_color:
                return v.gelato_sku
    except Exception:  # noqa: BLE001 - catalog blip: leave unresolved (held manual)
        return None
    return None


def wallart_cost_for(material: str, size: str) -> float | None:
    """Resolve a wall-art order's gelato_cost from its material + size label by
    matching the priced variation table, so the margin gate can actually evaluate
    wall-art orders (which otherwise carry no cost). Returns None when it cannot
    confidently match - the gate then simply doesn't fire rather than guess.

    Tolerant of display labels: "Framed - Oak", "Poster (unframed print)", etc.
    For an ambiguous framed match (frame colour not in the label) it returns the
    LOWEST candidate cost, so it never false-flags a real order as below floor.
    """
    if not material or not size:
        return None
    mat = str(material).lower()
    key = next((k for k in ("poster", "framed", "canvas", "acrylic", "metal")
                if k in mat), None)
    if key is None:
        return None
    try:
        # Match on a NORMALISED size: the storefront sends a bare token ("8x10")
        # while the catalog label carries a unit ("8x10 in"). Comparing them raw
        # never matched, so wall-art - the primary line - recorded NO cost.
        cands = [v for v in build_variations()
                 if v.material == key and _ns(v.size) == _ns(size)]
    except Exception:  # noqa: BLE001 - catalog/pricing blip: skip the check
        return None
    if not cands:
        return None
    if key == "framed":
        named = [v for v in cands if v.frame_color and v.frame_color.lower() in mat]
        if named:
            cands = named
    return min(v.gelato_cost for v in cands)


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
