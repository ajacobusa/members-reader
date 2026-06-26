"""Push per-order Etsy payouts into Wave as money transactions.

Each billable order becomes ONE Wave transaction that mirrors the corrected books:
  anchor : Bank/Clearing account, amount = net_payout, direction = DEPOSIT
  lines  : Sales income (INCREASE) + Shipping income (INCREASE) + Etsy fees (INCREASE)
so it BALANCES by construction (net_payout = sales + shipping - fees). Sales tax is
pass-through and never appears. externalId = "joffiels-<order>" makes the push
idempotent. Gelato COGS is intentionally NOT pushed - vendor charges arrive on your
bank/card feed in Wave; pushing the catalog estimate too would double-count.

For a real bank account, the API entry can duplicate the Etsy deposit your bank feed
imports. Best practice: point WAVE_ACCT_BANK at a dedicated "Etsy Clearing" account,
then record one transfer Clearing -> Bank per actual deposit. Run with dry_run first.
"""
from __future__ import annotations


def sync_period(period: str = "month", dry_run: bool = True) -> dict:
    """Build (and unless dry_run, push) a Wave transaction per billable order."""
    from quoteforge.config import (WAVE_BUSINESS_ID, WAVE_ACCT_BANK, WAVE_ACCT_SALES,
                                   WAVE_ACCT_SHIPPING, WAVE_ACCT_FEES)
    from quoteforge.etsy.books_export import bookkeeper_rows
    from quoteforge.etsy.wave_api import create_money_transaction

    rows = bookkeeper_rows(period)
    missing = [n for n, v in (("WAVE_BUSINESS_ID", WAVE_BUSINESS_ID),
                              ("WAVE_ACCT_BANK", WAVE_ACCT_BANK),
                              ("WAVE_ACCT_SALES", WAVE_ACCT_SALES),
                              ("WAVE_ACCT_FEES", WAVE_ACCT_FEES)) if not v]
    out = {"period": period, "orders": len(rows), "created": 0, "failed": 0,
           "dry_run": dry_run, "missing_config": missing, "errors": [], "txns": []}
    if missing and not dry_run:
        return out

    for r in rows:
        sales = round(float(r["sales_income"]), 2)
        ship = round(float(r["shipping_income"]), 2)
        fees = round(float(r["etsy_fees"]), 2)
        lines = [{"accountId": WAVE_ACCT_SALES, "amount": sales, "balance": "INCREASE"}]
        if ship > 0:
            if WAVE_ACCT_SHIPPING:
                lines.append({"accountId": WAVE_ACCT_SHIPPING, "amount": ship,
                              "balance": "INCREASE"})
            else:                                  # no shipping account -> fold into sales
                lines[0]["amount"] = round(lines[0]["amount"] + ship, 2)
        if fees > 0:
            lines.append({"accountId": WAVE_ACCT_FEES, "amount": fees,
                          "balance": "INCREASE"})
        anchor = {"accountId": WAVE_ACCT_BANK, "amount": round(float(r["net_payout"]), 2),
                  "direction": "DEPOSIT"}
        ext = f"joffiels-{r['order']}"
        desc = f"Etsy order {r['order']}"
        out["txns"].append({"externalId": ext, "date": r["date"], "anchor": anchor,
                            "lineItems": lines})
        if dry_run:
            continue
        res = create_money_transaction(WAVE_BUSINESS_ID, ext, r["date"], desc,
                                       anchor, lines)
        if res["ok"]:
            out["created"] += 1
        else:
            out["failed"] += 1
            out["errors"].append({"order": r["order"], "errors": res["errors"]})
    return out
