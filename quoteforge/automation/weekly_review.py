"""Weekly Friday business review - TCO + key metrics + AI commentary, emailed.

Gathers the metrics that matter (P&L, margin, AOV, TCO, orders, holds, list/
review growth), has Claude summarize wins/risks/next actions, and emails the
status to the owner. Scheduled every Friday. AI is TEST_MODE-safe.
"""
from __future__ import annotations


def collect_metrics() -> dict:
    m: dict = {}

    def _try(k, fn):
        try:
            m[k] = fn()
        except Exception as exc:  # noqa: BLE001
            m[k] = {"error": str(exc)}

    def _pnl():
        from quoteforge.etsy.ledger import build_ledger
        return build_ledger("month")["totals"]
    _try("pnl_month", _pnl)

    def _tco():
        from quoteforge.etsy.tco import live_tco
        return live_tco(listings=100)
    _try("tco", _tco)

    def _aov():
        p = m.get("pnl_month", {})
        rev, n = p.get("revenue", 0), p.get("orders", 0)
        return round(rev / n, 2) if n else 0.0
    _try("aov", _aov)

    def _counts():
        from quoteforge.db.database import (
            init_db, subscriber_count, review_stats, get_subscriptions,
            get_pending_approvals, get_all_orders)
        init_db()
        orders = get_all_orders(limit=100000)
        from collections import Counter
        st = Counter((o.get("status") or "?") for o in orders)
        return {"subscribers": subscriber_count(),
                "reviews": review_stats(),
                "active_subscriptions": len(get_subscriptions("active")),
                "pending_approvals": len(get_pending_approvals()),
                "orders_total": len(orders),
                "by_status": dict(st)}
    _try("counts", _counts)

    def _margins():
        from quoteforge.etsy.variations import build_variations
        vs = build_variations()
        return {"variations": len(vs),
                "below_floor": len([v for v in vs if v.margin_pct < 60])}
    _try("margins", _margins)
    return m


def weekly_review(email: bool = False) -> dict:
    import json
    from quoteforge.config import SHOP_NAME
    m = collect_metrics()
    p = m.get("pnl_month", {})
    from quoteforge.ai.assistant import ai_text
    fallback = (
        f"Weekly status for {SHOP_NAME}. Month-to-date: revenue "
        f"${p.get('revenue', 0)}, net ${p.get('net_profit', 0)} "
        f"({p.get('margin_pct', 0)}% margin), {p.get('orders', 0)} orders, "
        f"AOV ${m.get('aov', 0)}. Subscribers {m.get('counts', {}).get('subscribers', 0)}, "
        f"reviews {m.get('counts', {}).get('reviews', {})}. "
        f"Focus: drive traffic, convert, keep margin >=60%.")
    summary = ai_text(
        "You are a CFO/ops advisor for a personalized wall-art POD shop. From "
        "these JSON metrics write a brief Friday status (5-7 lines): the numbers "
        "that matter, 2 wins, 2 risks, and 3 prioritized actions for next week. "
        f"Be concrete.\n\nMETRICS:\n{json.dumps(m, default=str)}",
        operation="weekly_review", max_tokens=500, mock=fallback)
    try:
        from quoteforge.etsy.ledger import weekly_trend
        m["trend"] = weekly_trend(4)
    except Exception:  # noqa: BLE001
        m["trend"] = []
    report = {"metrics": m, "summary": summary}
    # Archive dated copies of the ledger + reconciliation + review to cost folder.
    try:
        report["archive"] = archive_cost_report(report)   # list of file paths
    except Exception:  # noqa: BLE001
        report["archive"] = []
    if email:
        try:
            from quoteforge.automation.emailer import _send_email
            from quoteforge.config import REPORT_RECIPIENT
            _send_email(f"{SHOP_NAME} - Friday Business Review",
                        format_review_html(report), to=REPORT_RECIPIENT,
                        attachments=report.get("archive") or None)
            report["emailed_to"] = REPORT_RECIPIENT
        except Exception:  # noqa: BLE001
            pass
    return report


def archive_cost_report(report: dict) -> list:
    """Save ledger.xlsx + reconciliation.xlsx + review.txt into a dated cost
    folder OUTPUT_DIR/cost/<YYYY>/<YYYY-MM-DD>/. Returns the archived file paths."""
    import shutil
    from datetime import date
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.etsy.ledger import export_ledger_excel
    today = date.today().isoformat()
    folder = OUTPUT_DIR / "cost" / today[:4] / today
    folder.mkdir(parents=True, exist_ok=True)
    paths = []

    led = export_ledger_excel("all")
    led_dest = folder / f"general_ledger_{today}.xlsx"
    shutil.copy2(led, led_dest)
    paths.append(str(led_dest))

    try:
        from quoteforge.etsy.reconciliation import export_reconciliation
        d = date.today()
        rec = export_reconciliation(d.year, d.month)
        rec_dest = folder / f"reconciliation_{d.year}-{d.month:02d}.xlsx"
        shutil.copy2(rec, rec_dest)
        paths.append(str(rec_dest))
    except Exception:  # noqa: BLE001
        pass

    (folder / f"business_review_{today}.txt").write_text(
        format_review_text(report), encoding="utf-8")
    return paths


def format_review_text(r: dict) -> str:
    m = r["metrics"]
    p = m.get("pnl_month", {})
    c = m.get("counts", {})
    tco = m.get("tco", {})
    lines = ["=" * 62, "FRIDAY BUSINESS REVIEW (TCO + key metrics)", "=" * 62,
             "\nAI SUMMARY:", r["summary"], "\nKEY METRICS (month-to-date):",
             f"  Revenue       : ${p.get('revenue', 0)}",
             f"  Net profit    : ${p.get('net_profit', 0)} ({p.get('margin_pct', 0)}%)",
             f"  Orders / AOV  : {p.get('orders', 0)} / ${m.get('aov', 0)}",
             f"  TCO (est.)    : {tco if isinstance(tco, dict) else tco}",
             f"  Subscribers   : {c.get('subscribers', 0)}",
             f"  Active subs   : {c.get('active_subscriptions', 0)}",
             f"  Reviews       : {c.get('reviews', {})}",
             f"  Pending appr. : {c.get('pending_approvals', 0)}",
             f"  Margins < 60% : {m.get('margins', {}).get('below_floor', 0)}"]
    trend = m.get("trend") or []
    if trend:
        lines.append("\n4-WEEK TREND (week of -> revenue / net / orders):")
        for w in trend:
            lines.append(f"  {w['week_of']}: ${w['revenue']} / ${w['net']} / "
                         f"{w['orders']}")
    lines.append("=" * 62)
    return "\n".join(lines)


def format_review_html(r: dict) -> str:
    return ("<html><body style='font-family:Arial'><pre style='font-size:13px;"
            f"white-space:pre-wrap'>{format_review_text(r)}</pre></body></html>")
