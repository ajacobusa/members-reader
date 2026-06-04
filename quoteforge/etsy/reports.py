"""Sales reports at four cadences: daily, weekly, monthly, yearly.

Each report aggregates the same financials (revenue, Etsy fees, sales tax,
Gelato cost, net profit) plus order-status counts over the chosen time window.
"""
from datetime import datetime, timedelta

from quoteforge.etsy.financials import summarize

PERIODS = ("daily", "weekly", "monthly", "yearly")


def period_window(period: str, now: datetime | None = None) -> tuple[datetime, str]:
    """Return (start_datetime, human_label) for the given period ending now."""
    now = now or datetime.now()
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = now.strftime("%A, %B %d, %Y")
    elif period == "weekly":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        label = f"Week ending {now.strftime('%B %d, %Y')}"
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = now.strftime("%B %Y")
    elif period == "yearly":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        label = now.strftime("Year %Y")
    else:
        raise ValueError(f"Unknown period: {period!r}. Use one of {PERIODS}.")
    return start, label


def period_report(period: str, now: datetime | None = None) -> dict:
    """Build a sales report for the period (daily/weekly/monthly/yearly)."""
    from quoteforge.db.database import get_all_orders
    now = now or datetime.now()
    start, label = period_window(period, now)

    orders = []
    for o in get_all_orders(limit=1000000):
        created = o.get("created_at", "") or ""
        try:
            dt = datetime.fromisoformat(created.replace("Z", ""))
        except ValueError:
            continue
        if dt >= start:
            orders.append(o)

    fin = summarize(orders)
    by_status: dict[str, int] = {}
    for o in orders:
        by_status[o.get("status", "")] = by_status.get(o.get("status", ""), 0) + 1

    return {
        "period": period,
        "label": label,
        "start": start.isoformat(),
        "end": now.isoformat(),
        "total_orders": len(orders),
        "by_status": by_status,
        "financials": fin,
    }


def format_report_text(report: dict) -> str:
    """Plain-text version of a period report (for CLI / email fallback)."""
    f = report["financials"]
    lines = [
        "=" * 52,
        f"QUOTEFORGE {report['period'].upper()} SALES REPORT",
        report["label"],
        "=" * 52,
        f"Orders in period   : {report['total_orders']}",
        f"Billable orders    : {f['order_count']}",
        "",
        f"Revenue (gross)    : ${f['revenue']:.2f}",
        f"Etsy fees          : -${f['etsy_fees']:.2f}",
        f"Gelato print cost  : -${f['gelato_cost']:.2f}",
        f"NET PROFIT         : ${f['net_profit']:.2f}",
        f"Avg profit/order   : ${f['avg_profit_per_order']:.2f}",
        f"Sales tax (Etsy remits, not income): ${f['sales_tax_collected']:.2f}",
        "=" * 52,
    ]
    return "\n".join(lines)
