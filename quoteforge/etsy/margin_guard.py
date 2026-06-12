"""Margin-floor guard — prevent silent margin erosion.

High-ticket POD guidance: hold a 50-70% gross margin and review costs regularly,
because platform price increases quietly eat into margins. This module checks any
price/cost pair against a target floor and audits the whole catalog (single
products + gallery sets), flagging anything that has slipped below it and the
minimum price that would restore the floor.
"""
from quoteforge.config import TARGET_MARGIN_PCT
from quoteforge.etsy.profit_calculator import (
    calculate_order_profit, ETSY_TRANSACTION_FEE, ETSY_PAYMENT_FEE,
    ETSY_LISTING_FEE,
)


def min_price_for_margin(gelato_cost: float, floor_pct: float) -> float:
    """Lowest sale price that still clears floor_pct net margin.

    net = price - gelato - price*(txn+pay) - listing_fee ;  net/price >= floor
    => price * (1 - fees - floor) >= gelato + listing_fee
    """
    fee_rate = ETSY_TRANSACTION_FEE + ETSY_PAYMENT_FEE
    denom = 1 - fee_rate - (floor_pct / 100.0)
    if denom <= 0:
        return float("inf")  # floor too high to ever achieve at these fees
    return round((gelato_cost + ETSY_LISTING_FEE) / denom, 2)


def margin_check(sale_price: float, gelato_cost: float,
                 floor_pct: float = None) -> dict:
    """Check one price/cost pair against the margin floor."""
    floor = TARGET_MARGIN_PCT if floor_pct is None else floor_pct
    p = calculate_order_profit(sale_price, gelato_cost)
    ok = p["margin_pct"] >= floor
    return {
        "sale_price": sale_price,
        "gelato_cost": gelato_cost,
        "margin_pct": p["margin_pct"],
        "net_profit": p["net_profit"],
        "floor_pct": floor,
        "ok": ok,
        "shortfall_pct": 0.0 if ok else round(floor - p["margin_pct"], 1),
        "min_price_for_floor": min_price_for_margin(gelato_cost, floor),
    }


def audit_catalog(floor_pct: float = None) -> dict:
    """Audit every single product AND gallery set against the margin floor."""
    floor = TARGET_MARGIN_PCT if floor_pct is None else floor_pct
    from quoteforge.etsy.product_lines import PRODUCT_LINES
    from quoteforge.etsy.gallery_sets import GALLERY_SETS

    rows = []
    for p in PRODUCT_LINES:
        c = margin_check(p.sell_price, p.gelato_cost, floor)
        rows.append({"name": p.name, "kind": "product", **c})
    for s in GALLERY_SETS:
        c = margin_check(s.set_price, s.gelato_cost, floor)
        rows.append({"name": s.name, "kind": "gallery set", **c})

    offenders = [r for r in rows if not r["ok"]]
    return {
        "floor_pct": floor,
        "checked": len(rows),
        "below_floor": len(offenders),
        "offenders": sorted(offenders, key=lambda r: r["margin_pct"]),
        "rows": rows,
    }


def format_audit_text(audit: dict) -> str:
    """Render the margin audit as printable console text."""
    lines = ["=" * 60,
             f"MARGIN GUARD - floor {audit['floor_pct']:.0f}% "
             f"({audit['checked']} items checked)", "=" * 60]
    if not audit["below_floor"]:
        lines.append(f"[OK] All {audit['checked']} items meet the "
                     f"{audit['floor_pct']:.0f}% margin floor.")
    else:
        lines.append(f"[WARN] {audit['below_floor']} item(s) below floor:")
        for r in audit["offenders"]:
            lines.append(f"  - {r['name']:30} {r['margin_pct']:>5.0f}% "
                         f"(need >= ${r['min_price_for_floor']:.2f} to hit "
                         f"{r['floor_pct']:.0f}%)")
        lines.append("\nFix: raise the price to the suggested minimum, or drop "
                     "the item. Re-run after Gelato/Etsy fee changes.")
    lines.append("=" * 60)
    return "\n".join(lines)
