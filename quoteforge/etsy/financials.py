"""Financial calculations for payments & bank reconciliation.

Turns the order database into a per-order ledger and period totals:
revenue, Etsy fees, sales tax (pass-through), Gelato cost, and net profit —
the numbers you reconcile against your Etsy, Gelato, and bank statements.
"""
from quoteforge.config import (
    DEFAULT_SALE_PRICE, DEFAULT_GELATO_COST, ESTIMATED_SALES_TAX_RATE,
)
from quoteforge.etsy.profit_calculator import calculate_order_profit


def order_financials(order: dict) -> dict:
    """Compute the full financial breakdown for one order.

    Uses the order's recorded sale_price / gelato_cost when present, otherwise
    falls back to the configured defaults (estimate). The 'estimated' flag tells
    you which orders used real numbers vs. defaults.
    """
    sale_price = order.get("sale_price")
    gelato_cost = order.get("gelato_cost")
    estimated = sale_price is None or gelato_cost is None
    sale_price = float(sale_price) if sale_price is not None else DEFAULT_SALE_PRICE
    gelato_cost = float(gelato_cost) if gelato_cost is not None else DEFAULT_GELATO_COST

    p = calculate_order_profit(sale_price, gelato_cost)
    # Sales tax Etsy collects & remits on your behalf — pass-through, not income
    sales_tax_collected = round(sale_price * ESTIMATED_SALES_TAX_RATE, 2)

    return {
        "order_id": order.get("order_id", ""),
        "etsy_order_id": order.get("etsy_order_id", "") or "",
        "occasion": order.get("occasion", ""),
        "status": order.get("status", ""),
        "created_at": (order.get("created_at", "") or "")[:10],
        "sale_price": sale_price,
        "etsy_fees": p["total_fees"],
        "sales_tax_collected": sales_tax_collected,  # remitted by Etsy, $0 net to you
        "gelato_cost": gelato_cost,
        "net_profit": p["net_profit"],
        "margin_pct": p["margin_pct"],
        "estimated": estimated,
    }


def summarize(orders: list[dict], billable_only: bool = True) -> dict:
    """Aggregate financial totals across a list of orders.

    billable_only: count only orders that represent real revenue (status in
    production/shipped/delivered) — pending/error orders haven't earned money.
    """
    billable_statuses = {"in_production", "shipped", "delivered",
                         "awaiting_customer_approval", "approved_ready_to_print",
                         "artwork_done"}
    rows = []
    for o in orders:
        if billable_only and o.get("status") not in billable_statuses:
            continue
        rows.append(order_financials(o))

    revenue = round(sum(r["sale_price"] for r in rows), 2)
    etsy_fees = round(sum(r["etsy_fees"] for r in rows), 2)
    tax = round(sum(r["sales_tax_collected"] for r in rows), 2)
    gelato = round(sum(r["gelato_cost"] for r in rows), 2)
    profit = round(sum(r["net_profit"] for r in rows), 2)
    return {
        "order_count": len(rows),
        "revenue": revenue,
        "etsy_fees": etsy_fees,
        "sales_tax_collected": tax,
        "gelato_cost": gelato,
        "net_profit": profit,
        "avg_profit_per_order": round(profit / len(rows), 2) if rows else 0.0,
        "rows": rows,
    }


def month_financials(year: int, month: int) -> dict:
    """Financial summary for a calendar month (for reconciliation/taxes)."""
    from quoteforge.db.database import get_all_orders
    prefix = f"{year:04d}-{month:02d}"
    orders = [o for o in get_all_orders(limit=100000)
              if (o.get("created_at", "") or "").startswith(prefix)]
    summary = summarize(orders)
    summary["period"] = prefix
    return summary
