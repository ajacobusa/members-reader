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


def _pdt(ts: str):
    """Parse an ISO/space timestamp to datetime, or None."""
    from datetime import datetime as _dt
    try:
        return _dt.fromisoformat((ts or "").replace("Z", "")[:26])
    except (ValueError, TypeError):
        return None


def _median(values: list) -> float:
    """Median of a numeric list (0.0 when empty)."""
    s = sorted(values)
    n = len(s)
    if not n:
        return 0.0
    mid = n // 2
    return round(s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2, 1)


def _days(a: str, b: str) -> float | None:
    """Whole days between two ISO timestamps (b - a), or None if unparseable."""
    from datetime import datetime as _dt
    try:
        return (_dt.fromisoformat((b or "").replace("Z", ""))
                - _dt.fromisoformat((a or "").replace("Z", ""))).days
    except (ValueError, TypeError):
        return None


def build_clv(orders: list[dict] | None = None) -> dict:
    """Per-customer rollup + headline CLV metrics from real orders, including
    time between purchases and a lapsed-customer win-back list.

    Pass `orders` (a prefetched list) to avoid re-querying the orders table.
    """
    from datetime import datetime as _dt
    from quoteforge.config import LAPSED_CUSTOMER_DAYS
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
            "last": o.get("created_at") or "", "_dates": []})
        c["orders"] += 1
        c["revenue"] = round(c["revenue"] + _price(o), 2)
        ca = o.get("created_at") or ""
        if ca:
            c["_dates"].append(ca)
            if not c["first"] or ca < c["first"]:
                c["first"] = ca
            if ca > c["last"]:
                c["last"] = ca

    from quoteforge.config import LAPSED_CUSTOMER_DAYS, CLV_DUE_SOON_DAYS
    now = _dt.now()
    now_iso = now.isoformat()
    for c in by_cust.values():
        # Gaps between consecutive orders -> avg + median interval.
        ds = sorted(d for d in (_pdt(x) for x in c.pop("_dates")) if d)
        gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
        c["avg_days_between"] = round(sum(gaps) / len(gaps), 1) if gaps else 0.0
        c["median_days_between"] = _median(gaps) if gaps else 0.0
        dsl = _days(c["last"], now_iso)
        c["days_since_last"] = dsl if dsl is not None else 0
        # Predicted next purchase = last order + typical (median) interval.
        interval = c["median_days_between"] or c["avg_days_between"]
        last_dt = _pdt(c["last"])
        if interval and last_dt:
            from datetime import timedelta as _td
            nxt = last_dt + _td(days=interval)
            c["predicted_next"] = nxt.date().isoformat()
            c["days_until_next"] = (nxt - now).days
        else:
            c["predicted_next"] = ""
            c["days_until_next"] = None

    customers = sorted(by_cust.values(), key=lambda c: c["revenue"], reverse=True)
    n_cust = len(customers)
    total_rev = round(sum(c["revenue"] for c in customers), 2)
    total_orders = sum(c["orders"] for c in customers)
    repeat = [c for c in customers if c["orders"] >= 2]
    avg_clv = round(total_rev / n_cust, 2) if n_cust else 0.0
    avg_orders = round(total_orders / n_cust, 2) if n_cust else 0.0
    aov = round(total_rev / total_orders, 2) if total_orders else 0.0
    repeat_rate = round(len(repeat) / n_cust * 100, 1) if n_cust else 0.0
    gaps = [c["avg_days_between"] for c in repeat if c["avg_days_between"]]
    avg_between = round(sum(gaps) / len(gaps), 1) if gaps else 0.0
    med_gaps = [c["median_days_between"] for c in repeat if c["median_days_between"]]
    median_between = _median(med_gaps) if med_gaps else 0.0
    # Win-back: customers who bought before but have gone quiet past the lapse
    # window (cheapest profit to recover), most-valuable first.
    winback = sorted(
        (c for c in customers if c["days_since_last"] >= LAPSED_CUSTOMER_DAYS),
        key=lambda c: c["revenue"], reverse=True)
    # Due-soon: repeat customers approaching their predicted next purchase (not
    # yet lapsed) - reach out BEFORE they disappear.
    due_soon = sorted(
        (c for c in repeat
         if c["days_until_next"] is not None
         and -CLV_DUE_SOON_DAYS <= c["days_until_next"] <= CLV_DUE_SOON_DAYS
         and c["days_since_last"] < LAPSED_CUSTOMER_DAYS),
        key=lambda c: (c["days_until_next"]))
    return {
        "customers": n_cust, "total_revenue": total_rev,
        "total_orders": total_orders, "avg_clv": avg_clv,
        "avg_orders_per_customer": avg_orders, "aov": aov,
        "repeat_customers": len(repeat), "repeat_rate_pct": repeat_rate,
        "avg_days_between_orders": avg_between,
        "median_days_between_orders": median_between,
        "lapsed_customers": len(winback),
        "winback": winback[:25],
        "due_soon": due_soon[:25],
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
        f"  Avg days between orders:  {c.get('avg_days_between_orders', 0)}",
        f"  Median days between:      {c.get('median_days_between_orders', 0)}",
        f"  Due soon (pre-empt):      {len(c.get('due_soon', []))}",
        f"  Lapsed (win-back):        {c.get('lapsed_customers', 0)}",
        "", "  Top customers by revenue:",
    ]
    for i, t in enumerate(c["top_customers"], 1):
        lines.append(f"   {i:>2}. {t['customer'][:28]:<28} "
                     f"{t['orders']} order(s)  ${t['revenue']:,.2f}")
    if c.get("winback"):
        lines.append("\n  Win-back (lapsed - re-engage these first):")
        for w in c["winback"][:8]:
            lines.append(f"   - {w['customer'][:28]:<28} "
                         f"${w['revenue']:,.2f}  ({w['days_since_last']}d quiet)")
    return "\n".join(lines)
