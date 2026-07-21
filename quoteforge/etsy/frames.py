"""Frame catalog — 3 high-end, 2 mid-range, 1 low-end frame tiers.

Each frame maps to a Gelato frame SKU and carries a modeled upcharge (added to
the base paper-print cost). Availability + cost are overridden live by the
Gelato sync via catalog_state, so a discontinued frame auto-disables and a price
change auto-reprices (pricing always re-derives from current cost to hold 60%).

Buyers can pick any frame on the Framed material; on Etsy they can add as many
framed (or other) items to the cart as they like — Etsy handles the cart.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Frame:
    """One frame option: tier, Gelato SKU, modeled upcharge, availability."""
    id: str
    name: str
    tier: str          # "high" | "mid" | "low"
    gelato_sku: str
    upcharge: float    # modeled USD added to the base print cost
    available: bool = True


# The defined ladder (3 high / 2 mid / 1 low). Costs are modeled until the
# Gelato sync overwrites them with live values.
FRAMES: list[Frame] = [
    # ── 3 high-end ──
    Frame("oak_premium", "Premium Solid Oak", "high", "GEL-FRAME-OAK-PRM", 22.0),
    Frame("walnut_premium", "Premium Walnut", "high", "GEL-FRAME-WAL-PRM", 24.0),
    Frame("gold_gallery", "Gallery Gold", "high", "GEL-FRAME-GLD-PRM", 26.0),
    # ── 2 mid-range ──
    Frame("black_wood", "Classic Black Wood", "mid", "GEL-FRAME-BLK-STD", 12.0),
    Frame("white_wood", "Classic White Wood", "mid", "GEL-FRAME-WHT-STD", 12.0),
    # ── 1 low-end ──
    Frame("slim_black", "Slim Black", "low", "GEL-FRAME-BLK-SLM", 7.0),
]

TIER_ORDER = {"high": 0, "mid": 1, "low": 2}


def _apply_overrides(f: Frame) -> Frame:
    """Return a copy of the frame with live availability/cost from the sync."""
    from quoteforge.etsy.catalog_state import sku_override
    ov = sku_override(f.gelato_sku)
    if not ov:
        return f
    return Frame(f.id, f.name, f.tier, f.gelato_sku,
                 ov.get("cost", f.upcharge), ov.get("available", f.available))


def all_frames() -> list[Frame]:
    """Every defined frame with live sync overrides applied."""
    return [_apply_overrides(f) for f in FRAMES]


def available_frames() -> list[Frame]:
    """Only frames the print partner can currently fulfill, high → low.

    Two gates (re-audit 2026-07-21, finding F1): the live sync's availability
    flag AND the approved-UID export - the docstring's promise was false while
    the hand-set flags said all six finishes existed but only black wood had an
    approved framed product. Every consumer (build_variations, options_block,
    frame previews, listing copy) inherits the truth from here. Grace mode
    (no framed UID exported yet) keeps the full ladder."""
    fr = [f for f in all_frames() if f.available]
    try:
        from quoteforge.etsy.fulfillability import approved_framed_finishes
        fin = approved_framed_finishes([f.name for f in fr])
        if fin is not None:
            fr = [f for f in fr if f.name in fin]
    except Exception as exc:  # noqa: BLE001 - fail open to the sync flags only
        import logging
        logging.getLogger(__name__).warning(
            "approved-finish filter unavailable (frames fall back to sync "
            "flags only): %s", exc)
    return sorted(fr, key=lambda f: (TIER_ORDER.get(f.tier, 9), -f.upcharge))


def frames_by_tier() -> dict[str, list[Frame]]:
    """Available frames grouped by tier (high / mid / low)."""
    out: dict[str, list[Frame]] = {"high": [], "mid": [], "low": []}
    for f in available_frames():
        out.setdefault(f.tier, []).append(f)
    return out
