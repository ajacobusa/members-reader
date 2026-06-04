"""Daily sales report emailer (Gmail SMTP).

Builds an HTML report from the order database (with demand-based tier
recommendations) and emails it to REPORT_RECIPIENT. Designed to be run once
a day via Windows Task Scheduler / cron:  python -m quoteforge.admin email-report
"""
import html
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from quoteforge.config import (
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD, REPORT_RECIPIENT, RENDERER,
)


def build_report_html() -> tuple[str, str]:
    """Build (subject, html_body) for the daily report. No network/SMTP here."""
    from quoteforge.db.database import init_db, daily_order_report
    from quoteforge.etsy.tier_advisor import recommend_tiers

    init_db()
    report = daily_order_report()
    by_status = report["by_status"]
    total = sum(by_status.values())
    shipped = by_status.get("shipped", 0)
    in_progress = sum(v for k, v in by_status.items()
                      if k not in ("shipped", "delivered", "error"))
    errors = by_status.get("error", 0)

    # Financial summary (revenue, Etsy fees, sales tax, Gelato cost, profit)
    from quoteforge.db.database import get_all_orders
    from quoteforge.etsy.financials import summarize
    fin = summarize(get_all_orders(limit=100000))

    # Demand-based tier recommendations (orders so far this run as a proxy)
    recs = recommend_tiers(monthly_orders=total, renderer=RENDERER)

    today = datetime.now().strftime("%A, %B %d, %Y")
    subject = f"QuoteForge Daily Report — {today} ({total} orders)"

    def _row(label: str, value) -> str:
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

    body = f"""\
<html><body style="font-family:Arial,sans-serif;color:#222">
  <h2 style="color:#1F4E79">QuoteForge Daily Sales Report</h2>
  <p>{today}</p>
  <table style="border-collapse:collapse;margin:12px 0">
    {_row("Total Orders", total)}
    {_row("In Progress", in_progress)}
    {_row("Shipped", shipped)}
    {_row("Errors", errors)}
  </table>

  <h3>💰 Financials (billable orders)</h3>
  <table style="border-collapse:collapse;margin:12px 0">
    {_row("Revenue (gross sales)", f"${fin['revenue']:.2f}")}
    {_row("Etsy Fees", f"-${fin['etsy_fees']:.2f}")}
    {_row("Gelato Print Cost", f"-${fin['gelato_cost']:.2f}")}
    {_row("NET PROFIT", f"${fin['net_profit']:.2f}")}
    {_row("Avg Profit / Order", f"${fin['avg_profit_per_order']:.2f}")}
    {_row("Sales Tax (collected & remitted by Etsy — not your money)", f"${fin['sales_tax_collected']:.2f}")}
  </table>

  <h3>Orders by Status</h3>
  <table style="border-collapse:collapse">{status_rows}</table>

  <h3>Pending Follow-ups</h3>
  <p>Unsent customer messages: <b>{report['unsent_messages']}</b> &nbsp;|&nbsp;
     Pending reviews: <b>{report['pending_reviews']}</b></p>

  <h3>Orders Needing Attention</h3>
  <ul>{attention_rows}</ul>

  {rec_block}

  <hr>
  <p style="font-size:12px;color:#888">
    Automated report from QuoteForge. Tier alerts are recommendations only —
    no subscription is changed automatically.</p>
</body></html>"""
    return subject, body


def send_daily_report() -> dict:
    """Build and email the daily report. Returns a status dict."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return {"status": "skipped",
                "message": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env"}

    subject, body = build_report_html()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = REPORT_RECIPIENT
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [REPORT_RECIPIENT], msg.as_string())

    return {"status": "sent", "to": REPORT_RECIPIENT, "subject": subject}
