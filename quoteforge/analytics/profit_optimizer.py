"""Profit Optimization Engine - which products/sizes/materials/sources actually
make the most money. Built from REAL orders only.

For every confirmed sale we compute true net profit (sale price - print cost -
Etsy fees) and roll it up across multiple dimensions: listing, material, size,
product type, channel, occasion, and acquisition source. Answers "what makes the
most money" and "what loses money", ranked. Pre-launch (no sales) it says so.
"""
from __future__ import annotations

# Dimensions we can slice by (order field -> human label).
DIMENSIONS = {
    "listing": "Listing",
    "material": "Material",
    "size": "Size",
    "product_type": "Product type",
    "channel": "Channel",
    "occasion": "Occasion",
    "acquisition_source": "Acquisition source",
}


def _confirmed_sales(orders: list[dict] | None = None) -> list[dict]:
    """Orders with a real sale price, annotated with computed net profit."""
    from quoteforge.db.database import init_db, get_all_orders
    from quoteforge.etsy.profit_calculator import calculate_order_profit
    init_db()
    rows = get_all_orders(limit=100000) if orders is None else orders
    out = []
    for o in rows:
        sale = o.get("sale_price")
        if sale in (None, 0):
            continue
        try:
            sale = float(sale)
        except (TypeError, ValueError):
            continue
        cost = 0.0
        try:
            cost = float(o.get("gelato_cost") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        p = calculate_order_profit(sale, cost)
        net = round(sale - cost - p["total_fees"], 2)
        d = dict(o)
        d["_net"] = net
        d["_revenue"] = sale
        d["_margin"] = round(net / sale * 100, 1) if sale else 0.0
        out.append(d)
    return out


def profit_by(dimension: str, orders: list[dict] | None = None) -> list[dict]:
    """Net profit rolled up by one dimension, best (most profit) first."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension: {dimension}")
    sales = _confirmed_sales(orders)
    agg: dict[str, dict] = {}
    for s in sales:
        key = (s.get(dimension) or "").strip() or "(unspecified)"
        a = agg.setdefault(key, {"key": key, "orders": 0, "revenue": 0.0,
                                 "net_profit": 0.0})
        a["orders"] += 1
        a["revenue"] = round(a["revenue"] + s["_revenue"], 2)
        a["net_profit"] = round(a["net_profit"] + s["_net"], 2)
    for a in agg.values():
        a["avg_profit"] = round(a["net_profit"] / a["orders"], 2) if a["orders"] else 0.0
        a["margin_pct"] = round(a["net_profit"] / a["revenue"] * 100, 1) if a["revenue"] else 0.0
    return sorted(agg.values(), key=lambda a: a["net_profit"], reverse=True)


def optimize(orders: list[dict] | None = None) -> dict:
    """Full profit picture across all dimensions + headline winners/losers."""
    sales = _confirmed_sales(orders)
    breakdowns = {dim: profit_by(dim, sales) for dim in DIMENSIONS}
    total_net = round(sum(s["_net"] for s in sales), 2)
    total_rev = round(sum(s["_revenue"] for s in sales), 2)

    def _top(dim):
        rows = breakdowns[dim]
        return rows[0] if rows else None

    insights = []
    for dim, label in DIMENSIONS.items():
        rows = [r for r in breakdowns[dim] if r["key"] != "(unspecified)"]
        if len(rows) >= 2:
            best, worst = rows[0], rows[-1]
            insights.append(
                f"{label}: '{best['key']}' makes the most "
                f"(${best['net_profit']:,.2f} net across {best['orders']} order(s)); "
                f"'{worst['key']}' the least (${worst['net_profit']:,.2f}).")
    return {
        "sales": len(sales), "total_revenue": total_rev,
        "total_net_profit": total_net,
        "overall_margin_pct": round(total_net / total_rev * 100, 1) if total_rev else 0.0,
        "breakdowns": breakdowns,
        "best_by_dimension": {dim: _top(dim) for dim in DIMENSIONS},
        "insights": insights,
    }


def format_profit_text(orders: list[dict] | None = None) -> str:
    o = optimize(orders)
    if not o["sales"]:
        return ("Profit Optimization Engine\n" + "-" * 44 +
                "\nNo confirmed sales yet - profit-per dimension will populate "
                "after your first orders.")
    lines = ["Profit Optimization Engine (real sales)", "-" * 44,
             f"  Confirmed sales : {o['sales']}",
             f"  Total revenue   : ${o['total_revenue']:,.2f}",
             f"  Net profit      : ${o['total_net_profit']:,.2f} "
             f"({o['overall_margin_pct']}%)", ""]
    for dim, label in DIMENSIONS.items():
        rows = [r for r in o["breakdowns"][dim] if r["key"] != "(unspecified)"]
        if not rows:
            continue
        lines.append(f"  By {label}:")
        for r in rows[:5]:
            lines.append(f"     {r['key'][:26]:<26} ${r['net_profit']:>9,.2f} net "
                         f"({r['orders']} ord, {r['margin_pct']}%)")
    if o["insights"]:
        lines.append("\n  Key insights:")
        for i in o["insights"]:
            lines.append(f"   - {i}")
    return "\n".join(lines)
