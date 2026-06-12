"""Subscription expiry reminders - automated, AI-personalized.

Finds subscriptions ending soon and emails each client a warm renewal reminder
(written by Claude, with a template fallback in TEST_MODE), BCC'ing the owner.
Idempotent: a subscription is only reminded once per end_date.
"""
from __future__ import annotations

from datetime import date


def _days_left(end_date: str) -> int:
    """Days from today until an ISO end date (0 if unparseable)."""
    try:
        return (date.fromisoformat(end_date[:10]) - date.today()).days
    except Exception:  # noqa: BLE001
        return 0


def send_expiry_reminders(within_days: int = 7, record: bool = True) -> dict:
    """Email a renewal reminder to every subscription ending within `within_days`.
    Returns a summary. Safe to run daily (idempotent per end_date)."""
    from quoteforge.config import SHOP_NAME
    from quoteforge.db.database import (
        init_db, get_expiring_subscriptions, mark_subscription_reminded)
    from quoteforge.ai.assistant import subscription_renewal_email
    init_db()
    due = get_expiring_subscriptions(within_days)
    sent = []
    for s in due:
        days = _days_left(s.get("end_date", ""))
        body_txt = subscription_renewal_email(
            s.get("customer_name", ""), s.get("plan", "subscription"), days, SHOP_NAME)
        if record:
            try:
                from quoteforge.automation.emailer import _send_email
                html = (f"<html><body style='font-family:Arial'>"
                        f"<pre style='font-size:14px;white-space:pre-wrap'>{body_txt}"
                        f"</pre></body></html>")
                _send_email(f"Your {SHOP_NAME} subscription is ending soon",
                            html, to=s.get("customer_email", ""))
                mark_subscription_reminded(s["id"])
            except Exception:  # noqa: BLE001
                pass
        sent.append({"email": s.get("customer_email"), "days_left": days})
    return {"due": len(due), "sent": sent}


def format_reminders_text(result: dict) -> str:
    """Render the reminder-run summary as printable console text."""
    lines = ["=" * 56, "SUBSCRIPTION EXPIRY REMINDERS", "=" * 56,
             f"  Due / reminded: {result['due']}"]
    for s in result["sent"]:
        lines.append(f"    {s['email']} - ends in {s['days_left']} day(s)")
    lines.append("=" * 56)
    return "\n".join(lines)
