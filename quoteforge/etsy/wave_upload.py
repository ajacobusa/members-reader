"""Wave transactions - the complete money picture for a period.

Used by BOTH the free CSV-upload path (write_wave_csv) and the automatic API push
(wave_sync). Every money movement is captured as a signed line carrying its Wave
account category, so income and ALL costs land in the books:

  + Etsy sale income            (tax-exclusive product revenue)   -> account 'sales'
  + Etsy shipping income        (direct sales only)               -> 'shipping'
  - Etsy fees                   (selling + processing)            -> 'fees'
  - Gelato print cost (COGS)                                      -> 'cogs'
  - Gelato shipping  (COGS)                                       -> 'cogs'
  - Infrastructure - <provider> (AI/API, itemised)               -> 'infra'
  - Infrastructure - hosting/software (prorated)                 -> 'infra'
  +/- Sales tax collected / remitted  (pass-through PAIR, nets to $0) -> 'tax'
  + Other income                (affiliate / wholesale)          -> 'other'

Sales tax is recorded as a collected(+)/remitted(-) pair so it is fully TRACKED but
never affects profit (Etsy collects AND remits it). wave_summary excludes the tax
pair from income/expense for that reason. Sum of all NON-tax rows = net profit.

CSV format: Date, Description, Amount (signed). Each row also carries `account`,
`balance` (INCREASE/DECREASE) and `ext` (idempotency id) for the API push.
"""
from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path

WAVE_COLUMNS = ["Date", "Description", "Amount"]


def wave_rows(period: str = "month") -> list[dict]:
    """Every income/cost line for the period (see module docstring)."""
    from quoteforge.etsy.ledger import _range_for, _daily_opex
    from quoteforge.db.database import (init_db, get_all_orders, get_api_costs,
                                        get_income)
    from quoteforge.etsy.financials import order_financials, BILLABLE_STATUSES
    init_db()
    start, end = _range_for(period)
    lo, hi = start.isoformat(), end.isoformat()
    hi_excl = (end + timedelta(days=1)).isoformat()
    rows: list[dict] = []

    def add(date, desc, amount, account, ext, balance="INCREASE"):
        """Append a signed line with its Wave account + idempotency id; skip $0."""
        amount = round(float(amount), 2)
        if amount:
            rows.append({"Date": (date or "")[:10], "Description": desc,
                         "Amount": amount, "account": account,
                         "balance": balance, "ext": ext})

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
        add(d, f"Etsy sale - order {ref}", f["product_revenue"] - ship, "sales", f"{ref}-sale")
        add(d, f"Etsy shipping income - order {ref}", ship, "shipping", f"{ref}-ship")
        add(d, f"Etsy fees - order {ref}", -f["etsy_fees"], "fees", f"{ref}-fees")
        add(d, f"Gelato print - order {ref}", -f["gelato_cost"], "cogs", f"{ref}-cogs")
        add(d, f"Gelato shipping - order {ref}", -f.get("gelato_shipping", 0),
            "cogs", f"{ref}-cogsship")
        # Sales tax PASS-THROUGH pair (net $0): collected (held), then remitted by Etsy.
        tax = round(float(f.get("sales_tax_collected") or 0), 2) if etsy_grandtotal else 0.0
        if tax:
            add(d, f"Sales tax collected (held by marketplace) - order {ref}",
                tax, "tax", f"{ref}-taxin", balance="INCREASE")
            add(d, f"Sales tax remitted by marketplace - order {ref}",
                -tax, "tax", f"{ref}-taxout", balance="DECREASE")

    # Infrastructure - AI/API costs (real, itemised).
    for c in get_api_costs(lo, hi_excl):
        prov = (c.get("provider") or "API").strip()
        op = (c.get("operation") or "").strip()
        label = f"Infrastructure - {prov}" + (f" ({op})" if op else "")
        add(c.get("created_at"), label, -(c.get("cost_usd") or 0), "infra",
            f"infra-{c.get('id', '')}")

    # Infrastructure - fixed hosting/software, prorated per day in range.
    opex = _daily_opex()
    if opex > 0:
        cur = start
        while cur <= end:
            add(cur.isoformat(), "Infrastructure - hosting/software (prorated)",
                -opex, "infra", f"opex-{cur.isoformat()}")
            cur += timedelta(days=1)

    # Other income (affiliate, wholesale, ...).
    for inc in get_income(lo, hi_excl):
        src = inc.get("source") or inc.get("note") or "misc"
        add(inc.get("day"), f"Other income - {src}", inc.get("amount") or 0,
            "other", f"other-{inc.get('id', inc.get('day', ''))}")

    rows.sort(key=lambda r: (r["Date"], r["Description"]))
    return rows


def wave_summary(period: str = "month") -> dict:
    """Period totals. Income/expense EXCLUDE the pass-through tax pair (net $0);
    tax_passthrough reports the tax tracked. net = income - expense."""
    rows = wave_rows(period)
    biz = [r for r in rows if r["account"] != "tax"]
    income = round(sum(r["Amount"] for r in biz if r["Amount"] > 0), 2)
    expense = round(sum(-r["Amount"] for r in biz if r["Amount"] < 0), 2)
    tax = round(sum(r["Amount"] for r in rows
                    if r["account"] == "tax" and r["Amount"] > 0), 2)
    return {"period": period, "lines": len(rows), "income": income,
            "expense": expense, "tax_passthrough": tax,
            "net": round(income - expense, 2)}


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
