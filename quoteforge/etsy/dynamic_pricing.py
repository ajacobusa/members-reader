"""Dynamic (seasonal-demand) pricing - UPLIFT ONLY, margin-safe by construction.

During an occasion's active marketing window we raise prices ABOVE the list price
by a capped percentage (top-revenue seasons weighted more). Because the multiplier
is always >= 1.0 and list price already clears the 68% list margin (>= the 60%
hard floor), a dynamic price can never fall below the floor. Off-peak the
multiplier is exactly 1.0 (list price). The whole feature is gated by
DYNAMIC_PRICING_ENABLED.
"""
from __future__ import annotations
from datetime import datetime


# Per-active-season uplift weight by revenue rank (rank 1 = biggest season).
def _season_weight(rank: int) -> float:
    if rank <= 1:
        return 0.10
    if rank <= 3:
        return 0.06
    return 0.03


# A season's demand window: this many days of run-up after marketing starts.
DEMAND_WINDOW_DAYS = 45


def active_seasons(now: datetime | None = None) -> list[dict]:
    """Seasons whose marketing window is currently active, with their uplift weight."""
    from quoteforge.etsy.marketing_calendar import ANNUAL_CALENDAR, _next_date
    now = now or datetime.now()
    out = []
    for s in ANNUAL_CALENDAR:
        # most recent marketing-start on/before today within the window
        start_this_year = _next_date(*s.marketing_starts, now)
        # _next_date returns the NEXT occurrence; step back a year if it's future
        start = start_this_year
        if start.date() > now.date():
            start = start.replace(year=start.year - 1)
        days_in = (now.date() - start.date()).days
        if 0 <= days_in <= DEMAND_WINDOW_DAYS:
            out.append({"occasion": s.occasion, "rank": s.revenue_rank,
                        "weight": _season_weight(s.revenue_rank),
                        "days_in": days_in})
    return sorted(out, key=lambda a: a["rank"])


def demand_multiplier(now: datetime | None = None) -> float:
    """Current price multiplier (>= 1.0). 1.0 when disabled or off-peak."""
    from quoteforge.config import DYNAMIC_PRICING_ENABLED, DYNAMIC_MAX_UPLIFT_PCT
    if not DYNAMIC_PRICING_ENABLED:
        return 1.0
    total = sum(s["weight"] for s in active_seasons(now))
    cap = DYNAMIC_MAX_UPLIFT_PCT / 100.0
    return round(1.0 + min(total, cap), 4)


def dynamic_price(list_price: float, cost: float = 0.0, tier: str = "entry",
                  now: datetime | None = None) -> dict:
    """Apply the uplift to a list price. Result is always >= list_price >= floor.

    Snaps to a .99-ending price for a clean storefront look while never rounding
    BELOW the list price (so margin only ever improves vs. list).
    """
    from quoteforge.etsy.variations import net_margin_pct, floor_for_tier
    from quoteforge.config import DYNAMIC_PRICING_ENABLED, DYNAMIC_MAX_UPLIFT_PCT
    seasons = active_seasons(now)          # computed once, reused below
    if not DYNAMIC_PRICING_ENABLED:
        mult = 1.0
    else:
        total = sum(s["weight"] for s in seasons)
        mult = round(1.0 + min(total, DYNAMIC_MAX_UPLIFT_PCT / 100.0), 4)
    raw = list_price * mult
    # round up to the next x.99 (>= raw), so we never round down below list
    import math
    price = round(math.ceil(raw + 0.001) - 0.01, 2) if mult > 1.0 else round(list_price, 2)
    if price < list_price:
        price = round(list_price, 2)
    margin = net_margin_pct(price, cost) if cost else None
    return {
        "list_price": round(list_price, 2), "price": price,
        "multiplier": mult, "uplift_pct": round((mult - 1.0) * 100, 1),
        "margin_pct": margin, "tier": tier,
        "holds_floor": (margin is None) or margin >= floor_for_tier(tier),
        "active_seasons": [s["occasion"] for s in seasons],
    }


def format_dynamic_text(now: datetime | None = None) -> str:
    from quoteforge.config import DYNAMIC_PRICING_ENABLED
    seasons = active_seasons(now)
    mult = demand_multiplier(now)
    lines = ["Dynamic pricing (seasonal demand)", "-" * 40,
             f"  Enabled        : {DYNAMIC_PRICING_ENABLED}",
             f"  Current uplift : +{round((mult - 1.0) * 100, 1)}% (x{mult})",
             f"  Active seasons : {', '.join(s['occasion'] for s in seasons) or 'none (off-peak)'}",
             "  Note: uplift-only - prices never drop below the 60% floor."]
    return "\n".join(lines)
