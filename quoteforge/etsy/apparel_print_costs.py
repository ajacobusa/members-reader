"""Extra apparel print-area pricing (back + sleeves).

The print partner does DTG on front/back/sleeves. The FRONT is in the base item price;
each EXTRA area adds an upcharge that clears the shop's target net margin PLUS
EXTRA_PRINT_MARGIN_PCT, AFTER the marketplace fee - so an extra print area is ALWAYS
profitable, never a loss. The per-order listing fee is already covered by the base item
and is not re-charged per area.

These are CUSTOM, made-to-order prints: once the buyer approves the proof of every
designed area, there is no return - so the proof + approval (handled in the editor)
must cover all areas before submit. This module only prices + names the areas.
"""
from __future__ import annotations

# The print partner's order-API placement 'type' values. 'default' == the front area.
FRONT_TYPE = "default"
SLEEVE_TYPES = ("sleeve-left", "sleeve-right")
EXTRA_TYPES = ("back",) + SLEEVE_TYPES          # everything billable beyond the front
_FRONT_ALIASES = {"", "front", "default"}


def area_cost(area: str) -> float:
    """High-end estimated partner print cost for ONE extra area (USD, overridable via
    env). Front/default is 0 (already in the base item price)."""
    from quoteforge.config import BACK_PRINT_COST, SLEEVE_PRINT_COST
    a = (area or "").strip().lower()
    if a in _FRONT_ALIASES:
        return 0.0
    if a.startswith("sleeve"):
        return float(SLEEVE_PRINT_COST)
    if a == "back":
        return float(BACK_PRINT_COST)
    return float(BACK_PRINT_COST)               # unknown extra -> the dearer estimate (safe)


def _target_margin_pct() -> float:
    from quoteforge.config import TARGET_MARGIN_PCT, EXTRA_PRINT_MARGIN_PCT
    return float(TARGET_MARGIN_PCT) + float(EXTRA_PRINT_MARGIN_PCT)


def _fee_rate() -> float:
    from quoteforge.etsy.margin_guard import ETSY_TRANSACTION_FEE, ETSY_PAYMENT_FEE
    return ETSY_TRANSACTION_FEE + ETSY_PAYMENT_FEE


def area_upcharge(area: str) -> float:
    """Buyer upcharge for ONE extra area: its cost grossed up so the net (after the
    marketplace fee) clears the target margin. Loss-proof. 0 for front/default."""
    cost = area_cost(area)
    if cost <= 0:
        return 0.0
    denom = 1.0 - _fee_rate() - _target_margin_pct() / 100.0
    if denom <= 0:
        return float("inf")                      # margin target unachievable at these fees
    return round(cost / denom, 2)


def _norm_areas(areas) -> list:
    """De-dupe + drop the front; keep only billable extra areas, normalized."""
    out, seen = [], set()
    for a in areas or []:
        a = (a or "").strip().lower()
        if a in _FRONT_ALIASES or a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


def extra_print_upcharge(areas) -> float:
    """Total upcharge for ALL extra print areas on an order (front excluded)."""
    return round(sum(area_upcharge(a) for a in _norm_areas(areas)), 2)


def margin_breakdown(area: str) -> dict:
    """{area, cost, upcharge, net_profit, margin_pct} for reporting/guards."""
    up, cost = area_upcharge(area), area_cost(area)
    net = round(up - cost - up * _fee_rate(), 2) if up not in (0.0, float("inf")) else 0.0
    return {"area": area, "cost": round(cost, 2), "upcharge": up,
            "net_profit": net, "margin_pct": round(net / up * 100, 1) if up else 0.0}
