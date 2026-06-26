"""Wave "Upload transactions" CSV - the FREE path (no Wave Pro / no bank feed).

Produces a bank-statement-style CSV capturing EVERY money movement for a period -
income and ALL costs - ready to drop into Wave: Sales & Payments -> Transactions ->
Upload transactions. Files land in a dedicated `wave/` folder, one per run, so a
daily job can write today's file and you upload it in one click.

Captured (signed Amount: + = money in, - = money out):
  + Etsy sale income            (tax-exclusive product revenue)
  + Etsy shipping income        (direct sales only; for Etsy it's inside the sale)
  - Etsy fees                   (selling + processing)
  - Gelato print cost (COGS)
  - Gelato shipping (COGS)
  - Infrastructure - <provider> (AI/API costs, itemised from api_costs)
  - Infrastructure - hosting/software (prorated daily from MONTHLY_FIXED_COSTS)
  + Other income                (affiliate / wholesale)
Sales tax is PASS-THROUGH (Etsy collects + remits) and is intentionally excluded.
The sum of all rows = your net profit for the period.
"""
from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path

WAVE_COLUMNS = ["Date", "Description", "Amount"]


def wave_rows(period: str = "month") -> list[dict]:
    """Every income/cost line for the period as {Date, Description, Amount}."""
    from quoteforge.etsy.ledger import _range_for, _daily_opex
    from quoteforge.db.database import (init_db, get_all_orders, get_api_costs,
                                        get_income)
    from quoteforge.etsy.financials import order_financials, BILLABLE_STATUSES
    init_db()
    start, end = _range_for(period)
    lo, hi = start.isoformat(), end.isoformat()
    hi_excl = (end + timedelta(days=1)).isoformat()
    rows: list[dict] = []

    def add(date, desc, amount):
        """Append a signed transaction line, skipping zero amounts."""
        amount = round(float(amount), 2)
        if amount:
            rows.append({"Date": (date or "")[:10], "Description": desc,
                         "Amount": amount})

    # Order-driven income + costs (billable orders only).
    for o in get_all_orders(limit=100000):
        d = (o.get("created_at") or "")[:10]
        if not (lo <= d <= hi):
            continue
        if o.get("status") not in BILLABLE_STATUSES or o.get("sale_price") in (None, 0):
            continue
        f = order_financials(o)
        ref = f["etsy_order_id"] or f["order_id"]
        etsy_grandtotal = o.get("tax_collected") is not None
        ship = 0.0 if etsy_grandtotal else round(f["shipping_collected"], 2)
        add(d, f"Etsy sale - order {ref}", f["product_revenue"] - ship)
        add(d, f"Etsy shipping income - order {ref}", ship)
        add(d, f"Etsy fees - order {ref}", -f["etsy_fees"])
        add(d, f"Gelato print - order {ref}", -f["gelato_cost"])
        add(d, f"Gelato shipping - order {ref}", -f.get("gelato_shipping", 0))

    # Infrastructure - AI/API costs (real, itemised).
    for c in get_api_costs(lo, hi_excl):
        prov = (c.get("provider") or "API").strip()
        op = (c.get("operation") or "").strip()
        label = f"Infrastructure - {prov}" + (f" ({op})" if op else "")
        add(c.get("created_at"), label, -(c.get("cost_usd") or 0))

    # Infrastructure - fixed hosting/software, prorated per day in range.
    opex = _daily_opex()
    if opex > 0:
        cur = start
        while cur <= end:
            add(cur.isoformat(),
                "Infrastructure - hosting/software (prorated)", -opex)
            cur += timedelta(days=1)

    # Other income (affiliate, wholesale, ...).
    for inc in get_income(lo, hi_excl):
        src = inc.get("source") or inc.get("note") or "misc"
        add(inc.get("day"), f"Other income - {src}", inc.get("amount") or 0)

    rows.sort(key=lambda r: (r["Date"], r["Description"]))
    return rows


def wave_summary(period: str = "month") -> dict:
    """Period totals - income, expense, and net (= sum of every signed line)."""
    rows = wave_rows(period)
    income = round(sum(r["Amount"] for r in rows if r["Amount"] > 0), 2)
    expense = round(sum(-r["Amount"] for r in rows if r["Amount"] < 0), 2)
    return {"period": period, "lines": len(rows), "income": income,
            "expense": expense, "net": round(income - expense, 2)}


def write_wave_csv(out_dir=None, period: str = "month") -> Path:
    """Write the period's transactions to wave/wave_<end>_<period>.csv."""
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.etsy.ledger import _range_for
    base = Path(out_dir) if out_dir else (Path(OUTPUT_DIR) / "wave")
    base.mkdir(parents=True, exist_ok=True)
    _, end = _range_for(period)
    path = base / f"wave_{end.isoformat()}_{period}.csv"
    rows = wave_rows(period)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(WAVE_COLUMNS)
        for r in rows:
            w.writerow([r["Date"], r["Description"], f"{r['Amount']:.2f}"])
    return path
