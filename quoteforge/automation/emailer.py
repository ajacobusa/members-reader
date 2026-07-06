"""Daily sales report emailer (Gmail SMTP).

Builds an HTML report from the order database (with demand-based tier
recommendations) and emails it to REPORT_RECIPIENT. Designed to be run once
a day via Windows Task Scheduler / cron:  python -m quoteforge.admin email-report
"""
import html
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

from quoteforge.config import (
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD, REPORT_RECIPIENT, RENDERER,
)


def build_report_html() -> tuple[str, str]:
    """Build (subject, html_body) for the daily report. No network/SMTP here."""
    from quoteforge.db.database import init_db, daily_order_report
    from quoteforge.etsy.tier_advisor import recommend_tiers

    init_db()
    report = daily_order_report()      # all-time status counts (outstanding work)
    by_status = report["by_status"]
    in_progress = sum(v for k, v in by_status.items()
                      if k not in ("shipped", "delivered", "error"))
    errors = by_status.get("error", 0)

    # TODAY's activity + financials (scoped to today — this is a *daily* report)
    from quoteforge.etsy.reports import period_report
    from quoteforge.etsy.financials import summarize
    from quoteforge.db.database import get_all_orders
    today_rep = period_report("daily")
    today_count = today_rep["total_orders"]
    fin = today_rep["financials"]                       # today's money
    all_time = summarize(get_all_orders(limit=100000))  # lifetime money (context)
    shipped = by_status.get("shipped", 0)

    # Demand-based tier recommendations (use this month's volume as the signal)
    monthly_orders = period_report("monthly")["total_orders"]
    recs = recommend_tiers(monthly_orders=monthly_orders, renderer=RENDERER)

    # Automated sales actions to send today (upsells / reviews / win-backs)
    from quoteforge.etsy.sales_engine import sales_actions_digest
    _sd = sales_actions_digest()
    sales = {"upsell_n": len(_sd["upsells"]), "review_n": len(_sd["reviews"]),
             "winback_n": len(_sd["winbacks"])}

    today = datetime.now().strftime("%A, %B %d, %Y")
    subject = f"QuoteForge Daily Report — {today} ({today_count} new orders today)"

    def _row(label: str, value) -> str:
        """Build one label/value HTML table row for the report."""
        return (f"<tr><td style='padding:6px 14px;border:1px solid #ddd'>{html.escape(label)}</td>"
                f"<td style='padding:6px 14px;border:1px solid #ddd;font-weight:bold'>{value}</td></tr>")

    status_rows = "".join(
        _row(status.replace("_", " ").title(), n) for status, n in sorted(by_status.items())
    ) or _row("No orders yet", 0)

    attention_rows = "".join(
        f"<li>[{html.escape(o['status'])}] {html.escape(o['order_id'])} — "
        f"{html.escape(o['recipient_name'])} ({html.escape(o['occasion'])})</li>"
        for o in report["needs_attention"]
    ) or "<li>None — all clear.</li>"

    if recs:
        rec_items = "".join(
            f"<li style='color:{'#c0392b' if r['status']=='OVER_LIMIT' else '#e67e22'}'>"
            f"{html.escape(r['message'])}</li>" for r in recs
        )
        rec_block = f"<h3>⚙️ Tier / Capacity Alerts</h3><ul>{rec_items}</ul>"
    else:
        rec_block = ("<h3>⚙️ Tier / Capacity</h3><p>All services within current "
                     "plan limits — no upgrade needed.</p>")

    # Today's API spend (detailed).
    try:
        from quoteforge.automation.cost_tracker import cost_report, format_cost_html
        cost_block = format_cost_html(cost_report("today"))
    except Exception:  # noqa: BLE001
        cost_block = ""

    # Pending owner setup reminders (resurface daily until cleared).
    try:
        from quoteforge.reminders import reminders_html
        cost_block += reminders_html()
    except Exception as exc:  # noqa: BLE001 - reminders are best-effort, but log
        logger.debug("reminders_html failed: %s", exc)

    body = f"""\
<html><body style="font-family:Arial,sans-serif;color:#222">
  <h2 style="color:#1F4E79">QuoteForge Daily Sales Report</h2>
  <p>{today}</p>
  <table style="border-collapse:collapse;margin:12px 0">
    {_row("New Orders Today", today_count)}
    {_row("In Progress (all)", in_progress)}
    {_row("Shipped (all)", shipped)}
    {_row("Errors (all)", errors)}
  </table>

  <h3>💰 Today's Financials</h3>
  <table style="border-collapse:collapse;margin:12px 0">
    {_row("Revenue (gross sales)", f"${fin['revenue']:.2f}")}
    {_row("Etsy Fees", f"-${fin['etsy_fees']:.2f}")}
    {_row("Gelato Print Cost", f"-${fin['gelato_cost']:.2f}")}
    {_row("NET PROFIT (today)", f"${fin['net_profit']:.2f}")}
    {_row("Avg Profit / Order", f"${fin['avg_profit_per_order']:.2f}")}
    {_row("Sales Tax (collected & remitted by Etsy — not your money)", f"${fin['sales_tax_collected']:.2f}")}
  </table>

  <p style="font-size:13px;color:#555">
    All-time net profit: <b>${all_time['net_profit']:.2f}</b>
    across {all_time['order_count']} billable orders.</p>

  <h3>Orders by Status (all-time)</h3>
  <table style="border-collapse:collapse">{status_rows}</table>

  <h3>📈 Sales Actions to Send Today</h3>
  <p>Upsells: <b>{sales['upsell_n']}</b> &nbsp;|&nbsp;
     Review requests due: <b>{sales['review_n']}</b> &nbsp;|&nbsp;
     Repeat-buyer win-backs: <b>{sales['winback_n']}</b><br>
     <span style="font-size:12px;color:#555">Run
     <code>python -m quoteforge.admin sales</code> for the exact messages to send.</span></p>

  <h3>Pending Follow-ups</h3>
  <p>Unsent customer messages: <b>{report['unsent_messages']}</b> &nbsp;|&nbsp;
     Pending reviews: <b>{report['pending_reviews']}</b></p>

  <h3>Orders Needing Attention</h3>
  <ul>{attention_rows}</ul>

  {rec_block}

  {cost_block}

  <hr>
  <p style="font-size:12px;color:#888">
    Automated report from QuoteForge. Tier alerts are recommendations only —
    no subscription is changed automatically.</p>
</body></html>"""
    return subject, body


def send_cost_report(period: str = "today") -> dict:
    """Email a standalone detailed API cost report."""
    from quoteforge.automation.cost_tracker import cost_report, format_cost_html
    rep = cost_report(period)
    subject = (f"QuoteForge API Costs ({period}) — ${rep['total_cost']:.4f}, "
               f"{rep['calls']} calls")
    body = f"<html><body style='font-family:Arial'>{format_cost_html(rep)}</body></html>"
    return _send_email(subject, body)


def _send_count_path():
    """JSON file holding today's real-send count (per-day, resets on date change)."""
    from pathlib import Path
    from quoteforge.config import OUTPUT_DIR
    return Path(OUTPUT_DIR) / "email_send_count.json"


def _today_key() -> str:
    """UTC date key for the daily send budget."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sends_today() -> int:
    """Recipients emailed so far today (best-effort; 0 if the counter is unreadable)."""
    import json
    try:
        d = json.loads(_send_count_path().read_text(encoding="utf-8"))
        return int(d.get("count", 0)) if d.get("date") == _today_key() else 0
    except Exception:  # noqa: BLE001 - missing/corrupt counter -> treat as 0
        return 0


def _record_sends(n: int) -> None:
    """Add n recipients to today's send count (resets when the date rolls over)."""
    import json
    try:
        p = _send_count_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"date": _today_key(), "count": sends_today() + int(n)}),
                     encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - counter is best-effort
        logger.warning("email send counter write failed: %s", exc)


def _send_email(subject: str, body: str, to: str = "", attachments=None, *,
                critical: bool = False, force: bool = False, bcc_owner: bool = True) -> dict:
    """Send an HTML email via Gmail SMTP. Quota-safe:

    * NO real email in TEST_MODE (unless force=True) - so tests / dev / CI never burn the
      shared provider send quota. This is the guard that stops a customer email being
      dropped because a test run exhausted the daily cap.
    * CUSTOMER transactional email passes critical=True and ALWAYS sends (never deferred,
      never owner-BCC'd). NON-critical email (reports, digests, marketing) is DEFERRED once
      the day's send count reaches EMAIL_DAILY_BUDGET, preserving headroom for customers,
      and the owner is alerted.
    Skips gracefully when Gmail credentials are not configured.
    """
    from quoteforge.config import TEST_MODE, EMAIL_DAILY_BUDGET
    if TEST_MODE and not force:
        return {"status": "skipped", "message": "TEST_MODE - no real email sent"}
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return {"status": "skipped",
                "message": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env"}
    if not critical and not force and sends_today() >= int(EMAIL_DAILY_BUDGET):
        logger.warning("email deferred - daily budget %s reached (non-critical: %s)",
                       EMAIL_DAILY_BUDGET, subject)
        _alert_budget_reached(subject)
        return {"status": "deferred",
                "message": f"daily send budget {EMAIL_DAILY_BUDGET} reached; "
                           "non-critical email deferred (customer email still sends)"}
    recipient = to or REPORT_RECIPIENT
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = recipient
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body, "html"))
    msg.attach(alt)
    for path in (attachments or []):
        try:
            from email.mime.base import MIMEBase
            from email import encoders
            from pathlib import Path as _P
            p = _P(path)
            if not p.exists():
                continue
            part = MIMEBase("application", "octet-stream")
            part.set_payload(p.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f'attachment; filename="{p.name}"')
            msg.attach(part)
        except Exception as exc:  # noqa: BLE001 - never block the email, but log
            logger.warning("email attachment skipped: %s", exc)
    # The owner (REPORT_RECIPIENT) is BCC'd on owner/report email so all such comms are
    # visible - but NOT on customer transactional email (bcc_owner=False): that both halves
    # the quota a customer send costs AND avoids the owner getting a copy of every buyer note.
    envelope = [recipient]
    bcc = REPORT_RECIPIENT if (bcc_owner and REPORT_RECIPIENT and REPORT_RECIPIENT != recipient) else ""
    if bcc:
        envelope.append(bcc)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, envelope, msg.as_string())
    _record_sends(len(envelope))                 # count recipients against the daily budget
    return {"status": "sent", "to": recipient, "bcc": bcc, "subject": subject}


def _alert_budget_reached(subject: str) -> None:
    """Alert the owner ONCE per day that the send budget is reached (so they see it coming
    before customer email is ever at risk). Best-effort; forced so it isn't self-deferred."""
    import json
    from pathlib import Path
    from quoteforge.config import OUTPUT_DIR
    flag = Path(OUTPUT_DIR) / "email_budget_alerted.json"
    try:
        if json.loads(flag.read_text(encoding="utf-8")).get("date") == _today_key():
            return                                # already alerted today
    except Exception as exc:  # noqa: BLE001 - no prior flag / unreadable -> proceed to alert
        logger.debug("budget alert flag unreadable (will alert): %s", exc)
    try:
        _send_email("QuoteForge - daily email budget reached",
                    f"<p>The daily email send budget was reached; non-critical email is "
                    f"being deferred to protect customer transactional email. First deferred: "
                    f"{subject}</p>", force=True, bcc_owner=False)
        flag.write_text(json.dumps({"date": _today_key()}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - alert is best-effort, never blocks
        logger.warning("budget alert failed: %s", exc)


def send_period_report(period: str) -> dict:
    """Email a daily/weekly/monthly/yearly sales report."""
    if period == "daily":
        return send_daily_report()
    from quoteforge.etsy.reports import period_report, format_report_text
    rep = period_report(period)
    f = rep["financials"]
    subject = (f"QuoteForge {period.title()} Report — {rep['label']} "
               f"(${f['net_profit']:.2f} profit)")
    body = (f"<html><body style='font-family:Arial'>"
            f"<pre style='font-size:14px'>{format_report_text(rep)}</pre>"
            f"</body></html>")
    return _send_email(subject, body)


def send_daily_report() -> dict:
    """Build and email the daily report. Returns a status dict."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return {"status": "skipped",
                "message": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env"}
    subject, body = build_report_html()
    return _send_email(subject, body)
