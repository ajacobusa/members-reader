"""End-to-end general ledger - daily revenue, expenses & net profit.

Captures EVERY cost so the bottom line is true:
  + Revenue        : order sale prices
  - COGS           : Gelato print cost per order
  - Etsy fees      : transaction 6.5% + payment 3% + $0.20 listing, per order
  - API cost       : Claude (Anthropic) usage from the cost log
  - OpEx           : fixed monthly overhead (Make.com + MONTHLY_FIXED_COSTS),
                     prorated per day
  = Net profit

Reads live data so it's always current; the daily job also persists a snapshot
per day for history/trends. Money figures are USD.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


def _daily_opex() -> float:
    from quoteforge.config import MONTHLY_FIXED_COSTS, USE_MAKE_COM, MAKE_COM_COST
    monthly = float(MONTHLY_FIXED_COSTS) + (MAKE_COM_COST if USE_MAKE_COM else 0.0)
    return round(monthly / 30.4, 4)


def _range_for(period: str):
    today = date.today()
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    if period == "month":
        return today.replace(day=1), today
    if period == "year":
        return today.replace(month=1, day=1), today
    return date(2020, 1, 1), today          # "all"


def _day_of(iso: str) -> str:
    try:
        return (iso or "")[:10] or date.today().isoformat()
    except Exception:  # noqa: BLE001
        return date.today().isoformat()


def build_ledger(period: str = "month") -> dict:
    """Compute the P&L by day for the period + totals."""
    from quoteforge.db.database import init_db, get_all_orders, get_api_costs
    from quoteforge.etsy.profit_calculator import calculate_order_profit
    init_db()
    start, end = _range_for(period)
    # Orders/API costs are timestamped in UTC; allow +1 day so a late-evening
    # local sale stamped "tomorrow" in UTC still counts.
    hi = (end + timedelta(days=1)).isoformat()
    days: dict[str, dict] = {}

    def _row(d):
        return days.setdefault(d, {"day": d, "revenue": 0.0, "cogs": 0.0,
                                   "etsy_fees": 0.0, "api_cost": 0.0,
                                   "opex": 0.0, "net_profit": 0.0, "orders": 0})

    for o in get_all_orders(limit=100000):
        d = _day_of(o.get("created_at"))
        if not (start.isoformat() <= d <= hi):
            continue
        sale = o.get("sale_price")
        if sale in (None, 0):
            continue                          # no confirmed sale price yet
        cost = o.get("gelato_cost") or 0.0
        p = calculate_order_profit(float(sale), float(cost))
        r = _row(d)
        r["revenue"] += p["sale_price"]
        r["cogs"] += p["gelato_cost"]
        r["etsy_fees"] += p["total_fees"]
        r["orders"] += 1

    for c in get_api_costs(start.isoformat(), (end + timedelta(days=1)).isoformat()):
        _row(_day_of(c.get("created_at")))["api_cost"] += float(c.get("cost_usd") or 0)

    # Prorated fixed overhead for each calendar day in range.
    opex = _daily_opex()
    cur = start
    while cur <= end:
        _row(cur.isoformat())["opex"] += opex
        cur += timedelta(days=1)

    rows = []
    for d in sorted(days):
        r = days[d]
        r["net_profit"] = round(r["revenue"] - r["cogs"] - r["etsy_fees"]
                                - r["api_cost"] - r["opex"], 2)
        for k in ("revenue", "cogs", "etsy_fees", "api_cost", "opex"):
            r[k] = round(r[k], 2)
        rows.append(r)

    tot = {k: round(sum(r[k] for r in rows), 2)
           for k in ("revenue", "cogs", "etsy_fees", "api_cost", "opex", "net_profit")}
    tot["orders"] = sum(r["orders"] for r in rows)
    tot["margin_pct"] = round(tot["net_profit"] / tot["revenue"] * 100, 1) \
        if tot["revenue"] else 0.0
    return {"period": period, "start": start.isoformat(), "end": end.isoformat(),
            "days": rows, "totals": tot}


def snapshot_today() -> dict:
    """Persist today's ledger row (run daily). Returns today's figures."""
    from quoteforge.db.database import upsert_ledger_snapshot
    led = build_ledger("today")
    row = led["days"][0] if led["days"] else {
        "revenue": 0, "cogs": 0, "etsy_fees": 0, "api_cost": 0,
        "opex": _daily_opex(), "net_profit": round(-_daily_opex(), 2), "orders": 0}
    upsert_ledger_snapshot(date.today().isoformat(), row)
    return row


def format_ledger_text(led: dict) -> str:
    t = led["totals"]
    lines = ["=" * 70,
             f"GENERAL LEDGER  ({led['period']}: {led['start']} -> {led['end']})",
             "=" * 70,
             f"{'Date':12}{'Rev':>9}{'COGS':>9}{'Fees':>8}{'API':>7}"
             f"{'OpEx':>7}{'Net':>9}{'Ord':>5}"]
    for r in led["days"]:
        lines.append(f"{r['day']:12}{r['revenue']:>9.2f}{r['cogs']:>9.2f}"
                     f"{r['etsy_fees']:>8.2f}{r['api_cost']:>7.2f}{r['opex']:>7.2f}"
                     f"{r['net_profit']:>9.2f}{r['orders']:>5}")
    lines += ["-" * 70,
              f"{'TOTAL':12}{t['revenue']:>9.2f}{t['cogs']:>9.2f}{t['etsy_fees']:>8.2f}"
              f"{t['api_cost']:>7.2f}{t['opex']:>7.2f}{t['net_profit']:>9.2f}"
              f"{t['orders']:>5}",
              f"Net margin: {t['margin_pct']}%   (Revenue {t['revenue']:.2f} - "
              f"COGS {t['cogs']:.2f} - Fees {t['etsy_fees']:.2f} - API "
              f"{t['api_cost']:.2f} - OpEx {t['opex']:.2f})",
              "=" * 70]
    return "\n".join(lines)


def export_ledger_excel(period: str = "all", out_path=None):
    """Write the ledger to an .xlsx workbook. Returns the path."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from quoteforge.config import OUTPUT_DIR
    led = build_ledger(period)
    wb = Workbook()
    ws = wb.active
    ws.title = "General Ledger"
    headers = ["Date", "Revenue", "COGS (Gelato)", "Etsy Fees", "API Cost",
               "OpEx", "Net Profit", "Orders"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in led["days"]:
        ws.append([r["day"], r["revenue"], r["cogs"], r["etsy_fees"],
                   r["api_cost"], r["opex"], r["net_profit"], r["orders"]])
    t = led["totals"]
    ws.append(["TOTAL", t["revenue"], t["cogs"], t["etsy_fees"], t["api_cost"],
               t["opex"], t["net_profit"], t["orders"]])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    out = out_path or (OUTPUT_DIR / "general_ledger.xlsx")
    from pathlib import Path
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
