"""Financial calculations for payments & bank reconciliation.

Turns the order database into a per-order ledger and period totals:
revenue, Etsy fees, sales tax (pass-through), Gelato cost, and net profit —
the numbers you reconcile against your Etsy, Gelato, and bank statements.
"""
from quoteforge.config import (
    DEFAULT_SALE_PRICE, DEFAULT_GELATO_COST, ESTIMATED_SALES_TAX_RATE,
)
from quoteforge.etsy.profit_calculator import calculate_order_profit

# Statuses that represent EARNED revenue. A refunded / cancelled / pending / error
# order is excluded from every revenue + profit total so the books can't book a
# sale that didn't (or no longer) stands. The ledger imports this so the daily P&L
# and the period summary can never disagree on what counts.
BILLABLE_STATUSES = {"in_production", "shipped", "delivered",
                     "awaiting_customer_approval", "approved_ready_to_print",
                     "artwork_done"}


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

    # Sales tax is Etsy's PASS-THROUGH (collected + remitted, $0 net to you). When
    # the order carries an ACTUAL tax figure, the recorded sale_price (Etsy grand
    # total) INCLUDES it, so revenue + margin must be computed on the tax-EXCLUSIVE
    # product revenue or both are overstated by the tax. Subtract only the ACTUAL
    # tax: a direct/storefront sale_price is the product subtotal (tax added later
    # at external checkout), so subtracting an estimate there would understate it.
    actual_tax = order.get("tax_collected")
    tax_in_sale = round(float(actual_tax), 2) if actual_tax is not None else 0.0
    product_revenue = round(sale_price - tax_in_sale, 2)

    # Gelato also bills YOU for shipping the item to the buyer (separate from what
    # the customer paid, which is already inside product_revenue). Deduct it as COGS
    # when recorded - never add shipping_collected here or it double-counts (it is
    # already part of the tax-exclusive product_revenue).
    gelato_shipping = round(float(order.get("shipping_cost") or 0), 2)
    p = calculate_order_profit(product_revenue, gelato_cost,
                               shipping_cost=gelato_shipping)
    # Fully-loaded view (contribution MINUS packaging/reprint reserve/marketing),
    # consistent with the TCO + operating-cost reporting. Period overhead stays
    # in the ledger (it's a time cost, not a per-order one).
    from quoteforge.etsy.profit_calculator import operating_order_profit
    op = operating_order_profit(product_revenue, gelato_cost)

    # Prefer ACTUAL Etsy figures (imported from the Etsy receipt / Orders CSV) over
    # estimates.
    actual_fees = order.get("etsy_fees_actual")
    actual_payout = order.get("net_payout")
    shipping_collected = round(float(order.get("shipping_collected") or 0), 2)
    has_actual = actual_fees is not None or actual_tax is not None
    sales_tax_collected = (round(float(actual_tax), 2) if actual_tax is not None
                           else round(sale_price * ESTIMATED_SALES_TAX_RATE, 2))
    etsy_fees = round(float(actual_fees), 2) if actual_fees is not None else p["total_fees"]
    if actual_payout is not None:
        net_payout = round(float(actual_payout), 2)
    elif actual_tax is not None:
        # Etsy grand-total sale_price already INCLUDES shipping + tax. The deposit is
        # the tax-exclusive product revenue (item + shipping) minus Etsy fees; tax is
        # remitted by Etsy and shipping is already inside product_revenue, so re-adding
        # shipping_collected here (the old code) double-counted it and left tax in.
        net_payout = round(product_revenue - etsy_fees, 2)
    else:
        # Direct/storefront: sale_price is the pre-shipping subtotal, so shipping
        # collected is separate income that lands in your account.
        net_payout = round(product_revenue + shipping_collected - etsy_fees, 2)

    return {
        "order_id": order.get("order_id", ""),
        "etsy_order_id": order.get("etsy_order_id", "") or "",
        "occasion": order.get("occasion", ""),
        "status": order.get("status", ""),
        "created_at": (order.get("created_at", "") or "")[:10],
        "sale_price": sale_price,                 # order grand total (for payout recon)
        "product_revenue": product_revenue,       # tax-EXCLUSIVE revenue (the real top line)
        "shipping_collected": shipping_collected,
        "etsy_fees": etsy_fees,
        "sales_tax_collected": sales_tax_collected,  # remitted by Etsy, $0 net to you
        "gelato_cost": gelato_cost,
        "gelato_shipping": gelato_shipping,       # Gelato's shipping charge to YOU (COGS)
        "net_payout": net_payout,                 # what actually lands in your account
        "net_profit": p["net_profit"],            # contribution (prices/floor)
        "margin_pct": p["margin_pct"],
        "operating_net_profit": op["net_profit"],  # fully loaded (after op costs)
        "operating_margin_pct": op["margin_pct"],
        "estimated": estimated,
        "source": "etsy_actual" if has_actual else "estimated",
    }


def summarize(orders: list[dict], billable_only: bool = True) -> dict:
    """Aggregate financial totals across a list of orders.

    billable_only: count only orders that represent real revenue (status in
    production/shipped/delivered) — pending/error orders haven't earned money.
    """
    rows = []
    for o in orders:
        if billable_only and o.get("status") not in BILLABLE_STATUSES:
            continue
        rows.append(order_financials(o))

    # Revenue is the tax-EXCLUSIVE product revenue (sales tax is a pass-through,
    # not income). Grand total is summed separately for payout reconciliation.
    revenue = round(sum(r["product_revenue"] for r in rows), 2)
    gross_total = round(sum(r["sale_price"] for r in rows), 2)
    etsy_fees = round(sum(r["etsy_fees"] for r in rows), 2)
    tax = round(sum(r["sales_tax_collected"] for r in rows), 2)
    gelato = round(sum(r["gelato_cost"] for r in rows), 2)
    gelato_ship = round(sum(r.get("gelato_shipping", 0) for r in rows), 2)
    net_payout = round(sum(r["net_payout"] for r in rows), 2)
    profit = round(sum(r["net_profit"] for r in rows), 2)
    return {
        "order_count": len(rows),
        "revenue": revenue,                       # tax-exclusive product revenue
        "gross_total": gross_total,               # grand total incl. tax (payout recon)
        "etsy_fees": etsy_fees,
        "sales_tax_collected": tax,
        "gelato_cost": gelato,
        "gelato_shipping": gelato_ship,           # Gelato shipping COGS
        "net_payout": net_payout,                 # real cash-in (for bank reconciliation)
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
