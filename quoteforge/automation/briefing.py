"""Morning briefing — one consolidated daily ops read.

The shop has many specialised agents (retention, seasonal SEO, delight, growth,
approvals, reminders, health...). Reading a separate email from each is noise.
This aggregates everything that needs the owner's attention TODAY into a single
prioritised briefing, so you read one email and know exactly what to do.

Every section is best-effort: if one agent errors, the briefing still renders.
"""
from datetime import datetime


def _safe(fn, default):
    """Run fn(), returning `default` if it raises - keeps the briefing rendering."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def morning_briefing(now: datetime | None = None) -> dict:
    """Aggregate every agent's daily signals into one prioritised briefing dict."""
    now = now or datetime.now()
    from quoteforge.db.database import (
        init_db, get_order_stats, get_orders_by_status, get_pending_approvals,
    )
    init_db()

    stats = _safe(get_order_stats, {"total": 0, "by_status": {}})
    errored = _safe(lambda: get_orders_by_status("error"), [])
    photo_holds = _safe(lambda: get_orders_by_status("needs_better_photo"), [])
    awaiting = _safe(lambda: get_orders_by_status("awaiting_customer_approval"), [])
    approvals = _safe(get_pending_approvals, [])
    reminders = _safe(lambda: __import__(
        "quoteforge.reminders", fromlist=["get_reminders"]).get_reminders(), [])

    retention = _safe(lambda: __import__(
        "quoteforge.etsy.retention", fromlist=["retention_digest"]
    ).retention_digest(now), {"repeat_gift": [], "cross_sell": [], "lapsed": []})
    seasonal = _safe(lambda: __import__(
        "quoteforge.etsy.seasonal_seo", fromlist=["seasonal_seo_plan"]
    ).seasonal_seo_plan(now), {"due": []})
    delight = _safe(lambda: __import__(
        "quoteforge.etsy.delight_loop", fromlist=["delight_due"]
    ).delight_due(__import__("quoteforge.db.database", fromlist=["get_all_orders"]
                            ).get_all_orders(limit=100000), now), [])
    health = _safe(lambda: __import__(
        "quoteforge.automation.healthcheck", fromlist=["run_healthcheck"]
    ).run_healthcheck(), {"overall": "?"})
    cost = _safe(lambda: __import__(
        "quoteforge.automation.cost_tracker", fromlist=["cost_report"]
    ).cost_report("today"), {"total_cost": 0, "calls": 0})

    # What needs action today (prioritised).
    actions = []
    if photo_holds:
        actions.append(f"{len(photo_holds)} order(s) HELD for a better photo "
                       f"(awaiting buyer resend)")
    if errored:
        actions.append(f"{len(errored)} order(s) in ERROR - investigate")
    if approvals:
        actions.append(f"{len(approvals)} decision(s) need your approval "
                       f"(admin approvals)")
    if awaiting:
        actions.append(f"{len(awaiting)} order(s) awaiting customer proof approval")
    if retention["repeat_gift"]:
        actions.append(f"{len(retention['repeat_gift'])} repeat-gift outreach due "
                       f"(admin retention)")
    if seasonal["due"]:
        actions.append(f"{len(seasonal['due'])} seasonal SEO action(s) due "
                       f"(admin seasonal-seo)")
    if delight:
        actions.append(f"{len(delight)} review+referral touch(es) due (admin delight)")

    return {
        "now": now.strftime("%Y-%m-%d"),
        "orders_total": stats["total"], "by_status": stats["by_status"],
        "actions": actions,
        "photo_holds": len(photo_holds), "errors": len(errored),
        "approvals": len(approvals), "awaiting_proof": len(awaiting),
        "repeat_gift": len(retention["repeat_gift"]),
        "cross_sell": len(retention["cross_sell"]),
        "lapsed": len(retention["lapsed"]),
        "seasonal_due": len(seasonal["due"]),
        "delight_due": len(delight),
        "reminders": [r["text"] for r in reminders],
        "health": health["overall"],
        "api_cost_today": cost["total_cost"], "api_calls_today": cost["calls"],
        "analytics": _safe(
            lambda: __import__("quoteforge.automation.analytics_report",
                               fromlist=["analytics_summary"]).analytics_summary(),
            {}),
    }


def format_briefing_text(b: dict) -> str:
    """Render the briefing dict as a readable plain-text email body."""
    lines = ["=" * 60, f"JOFFIELS MORNING BRIEFING - {b['now']}", "=" * 60,
             f"Health: {b['health']}   Orders: {b['orders_total']}   "
             f"API spend today: ${b['api_cost_today']:.4f}"]
    lines.append("\nACTION NEEDED TODAY:")
    if b["actions"]:
        for a in b["actions"]:
            lines.append(f"  -> {a}")
    else:
        lines.append("  Nothing urgent. Everything is on autopilot. [OK]")
    lines.append("\nGROWTH OPPORTUNITIES:")
    lines.append(f"  Repeat-gift outreach : {b['repeat_gift']}")
    lines.append(f"  Cross-sell           : {b['cross_sell']}")
    lines.append(f"  Win-back lapsed      : {b['lapsed']}")
    lines.append(f"  Seasonal SEO due     : {b['seasonal_due']}")
    lines.append(f"  Review/referral due  : {b['delight_due']}")
    if b.get("analytics"):
        lines.append("")
        from quoteforge.automation.analytics_report import format_analytics_text
        lines.append(format_analytics_text(b["analytics"]))
    if b["reminders"]:
        lines.append("\nSETUP REMINDERS:")
        for r in b["reminders"]:
            lines.append(f"  * {r}")
    lines.append("=" * 60)
    return "\n".join(lines)


def send_briefing(now: datetime | None = None) -> dict:
    """Build the briefing and email it; subject reflects how many actions are due."""
    b = morning_briefing(now)
    from quoteforge.automation.emailer import _send_email
    n_actions = len(b["actions"])
    subject = (f"Joffiels Briefing {b['now']}: "
               + (f"{n_actions} action(s) needed" if n_actions
                  else "all clear"))
    body = (f"<html><body style='font-family:Arial'><pre style='font-size:13px'>"
            f"{format_briefing_text(b)}</pre></body></html>")
    out = _send_email(subject, body)
    return {"status": out["status"], "briefing": b}
