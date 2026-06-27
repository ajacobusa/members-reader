"""Push the FULL money picture into Wave as money transactions - automatically.

Each signed line from wave_upload.wave_rows (income AND every cost: Etsy fees, Gelato
print + shipping, infrastructure/software, and the sales-tax pass-through pair)
becomes one categorized Wave transaction:
  anchor    : Bank/Clearing account, amount = |line|, DEPOSIT (+) or WITHDRAWAL (-)
  line item : the mapped category account, amount = |line|, balance INCREASE/DECREASE
externalId = "joffiels-<ref>" makes the push idempotent (re-running never duplicates).
Sales tax is recorded as a collected/remitted pair that nets to $0 - tracked, never
profit. Run a dry-run first; the daily job only pushes live when WAVE_AUTO_SYNC is on.

Tip: point WAVE_ACCT_BANK at a dedicated "Etsy Clearing" account so these don't
duplicate the deposits a connected bank feed would import.
"""
from __future__ import annotations

# wave_upload account key -> config attribute holding the Wave account id.
_ACCOUNT_KEYS = {
    "sales": "WAVE_ACCT_SALES", "shipping": "WAVE_ACCT_SHIPPING",
    "fees": "WAVE_ACCT_FEES", "cogs": "WAVE_ACCT_COGS",
    "infra": "WAVE_ACCT_INFRA", "tax": "WAVE_ACCT_TAX", "other": "WAVE_ACCT_SALES",
}


def _accounts() -> dict:
    """Resolve each category key to its configured Wave account id (shipping/other
    fall back to the sales account when unset)."""
    import quoteforge.config as cfg
    out = {k: (getattr(cfg, attr, "") or "") for k, attr in _ACCOUNT_KEYS.items()}
    if not out["shipping"]:
        out["shipping"] = out["sales"]
    return out


def sync_period(period: str = "month", dry_run: bool = True) -> dict:
    """Build (and unless dry_run, push) one Wave transaction per income/cost line."""
    import quoteforge.config as cfg
    from quoteforge.etsy.wave_upload import wave_rows
    from quoteforge.etsy.wave_api import create_money_transaction

    rows = wave_rows(period)
    acct = _accounts()
    bank = getattr(cfg, "WAVE_ACCT_BANK", "") or ""
    used = {r["account"] for r in rows}
    missing = []
    if not (getattr(cfg, "WAVE_BUSINESS_ID", "") or ""):
        missing.append("WAVE_BUSINESS_ID")
    if not bank:
        missing.append("WAVE_ACCT_BANK")
    for k in sorted(used):
        if not acct.get(k):
            missing.append(_ACCOUNT_KEYS[k])
    out = {"period": period, "lines": len(rows), "created": 0, "failed": 0,
           "dry_run": dry_run, "missing_config": sorted(set(missing)),
           "errors": [], "txns": []}
    if out["missing_config"] and not dry_run:
        return out

    for r in rows:
        amt = round(abs(r["Amount"]), 2)
        direction = "DEPOSIT" if r["Amount"] > 0 else "WITHDRAWAL"
        anchor = {"accountId": bank, "amount": amt, "direction": direction}
        line = {"accountId": acct.get(r["account"]) or acct["sales"], "amount": amt,
                "balance": r.get("balance", "INCREASE")}
        ext = f"joffiels-{r['ext']}"
        out["txns"].append({"externalId": ext, "date": r["Date"],
                            "account": r["account"], "anchor": anchor,
                            "lineItems": [line]})
        if dry_run:
            continue
        res = create_money_transaction(cfg.WAVE_BUSINESS_ID, ext, r["Date"],
                                       r["Description"], anchor, [line])
        if res["ok"]:
            out["created"] += 1
        else:
            out["failed"] += 1
            out["errors"].append({"ext": ext, "errors": res["errors"]})
    return out
