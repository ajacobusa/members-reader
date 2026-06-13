"""Staged lapsed-customer win-back campaign - the highest-ROI marketing
automation (the acquisition cost is already paid).

A customer with no order in WINBACK_STAGES[0] days enters the sequence:
  Day 60  (stage 1): "We've added new designs" - re-engage, NO coupon.
  Day 90  (stage 2): a 10% come-back coupon.
  Day 120 (stage 3): a final, best offer (15%).

Each stage fires ONCE per lapse (tracked in winback_campaign, keyed to the
customer's last_order_at). A NEW order changes last_order_at, which resets the
sequence - a re-activated customer is no longer targeted and can lapse fresh
later. send=False is a read-only preview.
"""
from __future__ import annotations
from datetime import datetime

# (days_since_last threshold, stage, coupon_code, discount_pct). Stage 1 has no
# coupon - it's a soft "new designs" nudge before discounting.
WINBACK_STAGES = [
    (60, 1, None, 0),
    (90, 2, "COMEBACK10", 10),
    (120, 3, "COMEBACK15", 15),
]

_STAGE_COPY = {
    1: ("We've added new designs you might love",
        "It's been a while! We've added fresh personalized designs since your "
        "last order - come see what's new, your details are still saved."),
    2: ("A little something to welcome you back - 10% off",
        "We'd love to see you again. Here's {coupon} for 10% off your next "
        "personalized piece - because a gift from you means a lot."),
    3: ("Last chance: your best offer - 15% off",
        "One more from us: {coupon} takes 15% off your next order. We'd be "
        "delighted to make something special for you again."),
}


def _parse(ts: str) -> datetime | None:
    """Parse an ISO/space timestamp, or None."""
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "")[:26])
    except (ValueError, TypeError):
        return None


def _last_order_by_customer(orders: list[dict]) -> dict:
    """email -> {last_at(str), last_dt, name, recipient} for the latest order."""
    out: dict = {}
    for o in orders:
        email = (o.get("customer_email") or "").strip().lower()
        if not email:
            continue
        dt = _parse(o.get("created_at", ""))
        if dt is None:
            continue
        cur = out.get(email)
        if cur is None or dt > cur["last_dt"]:
            out[email] = {"last_at": o.get("created_at", ""), "last_dt": dt,
                          "name": o.get("customer_name") or email,
                          "recipient": o.get("recipient_name", "")}
    return out


def _due_stage(days_since: float, already_sent: int) -> tuple:
    """The highest win-back stage now due past what was already sent, as
    (stage, coupon, pct) - or (0, None, 0) when nothing is due."""
    due = (0, None, 0)
    for thresh, stage, coupon, pct in WINBACK_STAGES:
        if days_since >= thresh and stage > already_sent:
            due = (stage, coupon, pct)
    return due


def due_winbacks(orders: list[dict] | None = None,
                 now: datetime | None = None) -> list[dict]:
    """Lapsed customers due for their next win-back stage (read-only)."""
    from quoteforge.db.database import (init_db, get_all_orders,
                                        get_winback_state)
    init_db()
    now = now or datetime.now()
    if orders is None:
        orders = [o for o in get_all_orders(100000)
                  if o.get("status") not in (None, "error")]
    out = []
    for email, info in _last_order_by_customer(orders).items():
        days_since = (now - info["last_dt"]).days
        st = get_winback_state(email)
        # A new order (different last_order_at) means a fresh lapse: stage 0.
        sent = st["stage"] if st.get("last_order_at") == info["last_at"] else 0
        stage, coupon, pct = _due_stage(days_since, sent)
        if stage:
            subj, body = _STAGE_COPY[stage]
            out.append({"email": email, "customer": info["name"],
                        "recipient": info["recipient"], "stage": stage,
                        "coupon": coupon, "discount_pct": pct,
                        "days_since": days_since, "last_order_at": info["last_at"],
                        "subject": subj,
                        "message": body.format(coupon=coupon or "")})
    return sorted(out, key=lambda x: -x["days_since"])


def run_winback(send: bool = False, now: datetime | None = None) -> dict:
    """Send each due win-back email (send=True also records the stage so it
    fires once). send=False is a read-only preview."""
    from quoteforge.db.database import set_winback_stage
    items = due_winbacks(now=now)
    sent_items = []
    for it in items:
        if send:
            try:
                from quoteforge.automation.emailer import _send_email
                html = (f"<html><body style='font-family:Arial'>"
                        f"<p>{it['message']}</p></body></html>")
                _send_email(it["subject"], html, to=it["email"])
            except Exception:  # noqa: BLE001
                pass
            set_winback_stage(it["email"], it["stage"], it["last_order_at"])
            sent_items.append(it)
    return {"candidates": len(items), "sent": len(sent_items),
            "sent_items": sent_items, "preview": items}


def format_winback_text(now: datetime | None = None) -> str:
    """Plain-text preview of who is due for which win-back stage."""
    items = due_winbacks(now=now)
    lines = ["Win-back campaign (lapsed customers)", "-" * 40]
    if not items:
        lines.append("  No lapsed customers due - nice retention!")
        return "\n".join(lines)
    for it in items:
        coup = f" [{it['coupon']} {it['discount_pct']}%]" if it["coupon"] else ""
        lines.append(f"  Stage {it['stage']}  {it['customer'][:26]:<26} "
                     f"{it['days_since']}d quiet{coup}")
    return "\n".join(lines)
