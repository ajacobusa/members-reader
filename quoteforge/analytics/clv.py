"""Customer Lifetime Value (CLV) analytics - built from REAL orders only.

Aggregates the orders table by customer (email) to surface lifetime value, repeat
behavior, and the highest-value customers. Pre-launch (no orders) every number is
zero and the report says so plainly - no projected/fabricated CLV.
"""
from __future__ import annotations


def _orders() -> list[dict]:
    """All orders from the DB, or an empty list if the query fails."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    try:
        return get_all_orders(limit=100000)
    except Exception:  # noqa: BLE001
        return []


def _price(o: dict) -> float:
    """Sale price of an order as a float, 0.0 when missing or malformed."""
    try:
        return float(o.get("sale_price") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_clv(orders: list[dict] | None = None) -> dict:
    """Per-customer rollup + headline CLV metrics from real orders.

    Pass `orders` (a prefetched list) to avoid re-querying the orders table.
    """
    orders = _orders() if orders is None else orders
    by_cust: dict[str, dict] = {}
    for o in orders:
        key = (o.get("customer_email") or o.get("customer_name") or "").strip().lower()
        if not key:
            continue
        c = by_cust.setdefault(key, {
            "customer": o.get("customer_name") or o.get("customer_email") or key,
            "email": o.get("customer_email") or "",
            "orders": 0, "revenue": 0.0, "first": o.get("created_at") or "",
            "last": o.get("created_at") or ""})
        c["orders"] += 1
        c["revenue"] = round(c["revenue"] + _price(o), 2)
        ca = o.get("created_at") or ""
        if ca and (not c["first"] or ca < c["first"]):
            c["first"] = ca
        if ca and ca > c["last"]:
            c["last"] = ca

    customers = sorted(by_cust.values(), key=lambda c: c["revenue"], reverse=True)
    n_cust = len(customers)
    total_rev = round(sum(c["revenue"] for c in customers), 2)
    total_orders = sum(c["orders"] for c in customers)
    repeat = [c for c in customers if c["orders"] >= 2]
    avg_clv = round(total_rev / n_cust, 2) if n_cust else 0.0
    avg_orders = round(total_orders / n_cust, 2) if n_cust else 0.0
    aov = round(total_rev / total_orders, 2) if total_orders else 0.0
    repeat_rate = round(len(repeat) / n_cust * 100, 1) if n_cust else 0.0
    return {
        "customers": n_cust, "total_revenue": total_rev,
        "total_orders": total_orders, "avg_clv": avg_clv,
        "avg_orders_per_customer": avg_orders, "aov": aov,
        "repeat_customers": len(repeat), "repeat_rate_pct": repeat_rate,
        "top_customers": customers[:10],
    }


def format_clv_text(clv: dict | None = None, orders: list[dict] | None = None) -> str:
    """Plain-text CLV report (headline metrics + top customers by revenue)."""
    c = clv if clv is not None else build_clv(orders)
    if not c["customers"]:
        return ("Customer Lifetime Value\n" + "-" * 40 +
                "\nNo orders yet - CLV metrics will populate after your first sale.")
    lines = [
        "Customer Lifetime Value", "-" * 40,
        f"  Customers (with orders): {c['customers']}",
        f"  Total revenue:           ${c['total_revenue']:,.2f}",
        f"  Average CLV:             ${c['avg_clv']:,.2f}",
        f"  Avg orders / customer:   {c['avg_orders_per_customer']}",
        f"  Average order value:     ${c['aov']:,.2f}",
        f"  Repeat customers:        {c['repeat_customers']} ({c['repeat_rate_pct']}%)",
        "", "  Top customers by revenue:",
    ]
    for i, t in enumerate(c["top_customers"], 1):
        lines.append(f"   {i:>2}. {t['customer'][:28]:<28} "
                     f"{t['orders']} order(s)  ${t['revenue']:,.2f}")
    return "\n".join(lines)
