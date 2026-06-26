"""Accountant-ready export for QuickBooks / Xero / Wave (or a bookkeeper).

Produces a per-order transaction REGISTER plus PERIOD TOTALS, using the canonical
financials values (tax-exclusive revenue, actual-or-estimated Etsy fees, Gelato
COGS incl. its shipping charge, and the REAL net payout). Because every figure
comes from order_financials, the export always agrees with the internal ledger -
no re-derivation, no double-count.

Accounting model (single-channel Etsy -> Gelato):
  * Sales income      = product revenue (tax-EXCLUSIVE; shipping is inside it for an
                        Etsy grand-total order, broken out for a direct subtotal sale)
  * Etsy fees         = selling expense
  * Gelato COGS       = product cost + Gelato's shipping charge to you
  * Sales tax         = PASS-THROUGH (Etsy collects + remits; $0 to your P&L)
  * Net payout        = what actually lands in your bank (= income - Etsy fees)
With the corrected payout, a per-order entry balances: net_payout + etsy_fees =
sales_income + shipping_income.
"""
from __future__ import annotations

import csv
from pathlib import Path

COLUMNS = ["date", "order", "description", "sales_income", "shipping_income",
           "etsy_fees", "gelato_cogs", "sales_tax_passthrough", "net_payout",
           "net_profit"]


def bookkeeper_rows(period: str = "month") -> list[dict]:
    """One row per BILLABLE order in the period, with accounting columns."""
    from quoteforge.etsy.ledger import _range_for
    from quoteforge.db.database import init_db, get_all_orders
    from quoteforge.etsy.financials import order_financials, BILLABLE_STATUSES
    init_db()
    start, end = _range_for(period)
    lo, hi = start.isoformat(), end.isoformat()
    rows = []
    for o in get_all_orders(limit=100000):
        d = (o.get("created_at") or "")[:10]
        if not (lo <= d <= hi):
            continue
        if o.get("status") not in BILLABLE_STATUSES or o.get("sale_price") in (None, 0):
            continue
        f = order_financials(o)
        # Shipping is already inside product_revenue for an Etsy grand-total order
        # (tax recorded); only a direct subtotal sale breaks it out as its own line.
        etsy_grandtotal = o.get("tax_collected") is not None
        ship_income = 0.0 if etsy_grandtotal else round(f["shipping_collected"], 2)
        rows.append({
            "date": f["created_at"],
            "order": f["etsy_order_id"] or f["order_id"],
            "description": (o.get("occasion") or "Order").replace(",", " "),
            "sales_income": round(f["product_revenue"] - ship_income, 2),
            "shipping_income": ship_income,
            "etsy_fees": round(f["etsy_fees"], 2),
            "gelato_cogs": round(f["gelato_cost"] + f.get("gelato_shipping", 0), 2),
            "sales_tax_passthrough": round(f["sales_tax_collected"], 2),
            "net_payout": round(f["net_payout"], 2),
            "net_profit": round(f["net_profit"], 2),
        })
    return rows


def books_summary(period: str = "month") -> dict:
    """Period TOTALS - the numbers for one monthly journal entry."""
    rows = bookkeeper_rows(period)
    tot = {c: round(sum(float(r[c]) for r in rows), 2)
           for c in COLUMNS if c not in ("date", "order", "description")}
    tot["order_count"] = len(rows)
    tot["period"] = period
    # Sanity: with the corrected payout each order balances, so should the period.
    tot["balances"] = abs((tot["net_payout"] + tot["etsy_fees"])
                          - (tot["sales_income"] + tot["shipping_income"])) < 0.05
    return tot


def write_books_csv(path, period: str = "month") -> Path:
    """Write the per-order register to CSV (UTF-8) and return the path."""
    rows = bookkeeper_rows(period)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
        if rows:                                   # period TOTAL row for quick checks
            t = books_summary(period)
            w.writerow({"date": "", "order": "TOTAL", "description":
                        f"{t['order_count']} orders ({period})",
                        "sales_income": t["sales_income"],
                        "shipping_income": t["shipping_income"],
                        "etsy_fees": t["etsy_fees"], "gelato_cogs": t["gelato_cogs"],
                        "sales_tax_passthrough": t["sales_tax_passthrough"],
                        "net_payout": t["net_payout"], "net_profit": t["net_profit"]})
    return path
