import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from stock_dashboard.db.database import PickRecord
from stock_dashboard.engine.config_loader import Config

log = logging.getLogger(__name__)

_CATALYST_COLORS = {
    "earnings_beat": "#00c853",
    "analyst_upgrade": "#1565c0",
    "volume_breakout": "#e65100",
    "high_52w_breakout": "#6a1b9a",
    "guidance_raised": "#00838f",
    "price_target_increase": "#558b2f",
}


def build_html_email(picks: list[PickRecord], market_favorable: bool,
                     cfg: Config) -> str:
    today = date.today().strftime("%A, %B %d %Y")
    banner_color = "#00c853" if market_favorable else "#e53935"
    banner_text = (
        "Market conditions favorable"
        if market_favorable
        else "Market conditions unfavorable — no picks today"
    )

    rows = ""
    for i, p in enumerate(picks, 1):
        cats = p.catalysts if isinstance(p.catalysts, list) else []
        cat_badges = "".join(
            f'<span style="background:{_CATALYST_COLORS.get(c.get("type", ""), "#888")};'
            f'color:white;padding:2px 8px;border-radius:10px;font-size:11px;'
            f'margin-right:4px;">{c.get("label", c.get("type", ""))}</span>'
            for c in cats
        )
        narrative = p.narrative
        narrative_display = (
            narrative[:120] + "..." if len(narrative) > 120 else narrative
        )
        rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0;">
          <td style="padding:10px 8px;font-weight:700;color:#888;">{i}</td>
          <td style="padding:10px 8px;font-weight:800;color:#1565c0;font-size:15px;">{p.ticker}</td>
          <td style="padding:10px 8px;">{p.company}</td>
          <td style="padding:10px 8px;text-align:right;">${p.price:.2f}</td>
          <td style="padding:10px 8px;text-align:center;">
            <span style="background:#00c853;color:white;border-radius:50%;width:36px;height:36px;
            display:inline-flex;align-items:center;justify-content:center;font-weight:800;">
              {int(p.composite_score)}
            </span>
          </td>
          <td style="padding:10px 8px;">{cat_badges}</td>
          <td style="padding:10px 8px;color:#666;font-size:12px;">{narrative_display}</td>
        </tr>"""

    table_html = ""
    if picks:
        table_html = f"""
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead>
      <tr style="background:#f8f9fa;color:#555;">
        <th style="padding:8px;">#</th>
        <th style="padding:8px;">Ticker</th>
        <th style="padding:8px;">Company</th>
        <th style="padding:8px;">Price</th>
        <th style="padding:8px;">Score</th>
        <th style="padding:8px;">Catalysts</th>
        <th style="padding:8px;">Why Buy Today</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>"""

    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:20px;">
  <h1 style="color:#1a1a2e;">StockBoard — Top 10 Picks</h1>
  <p style="color:#888;">{today}</p>
  <div style="background:{banner_color};color:white;padding:10px 16px;border-radius:6px;margin-bottom:16px;">
    {banner_text}
  </div>
  {table_html}
  <hr style="margin-top:24px;">
  <p style="color:#aaa;font-size:12px;">
    Open dashboard for full breakdown &#x2192; <a href="http://localhost:8050">http://localhost:8050</a><br>
    This is not financial advice. Do your own research before trading.
  </p>
</body></html>"""


def send_email(subject: str, html_body: str, cfg: Config) -> None:
    ec = cfg.email
    if not ec.get("enabled"):
        log.info("Email disabled — skipping send")
        return
    if not ec.get("app_password"):
        log.warning("No Gmail App Password configured — skipping email send")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = ec["sender"]
    msg["To"] = ec["recipient"]
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as server:
            server.starttls()
            server.login(ec["sender"], ec["app_password"])
            server.sendmail(ec["sender"], ec["recipient"], msg.as_string())
        log.info("Email sent to %s", ec["recipient"])
    except Exception as exc:
        log.error("Failed to send email: %s", exc)
