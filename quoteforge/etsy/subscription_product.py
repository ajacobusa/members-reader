"""Subscription / membership product - listing + order activation.

Plans deliver a new personalized piece on a cadence (recurring revenue). When a
subscription order arrives, we create the subscription DB record (end date from
the plan) and send an AI welcome email. The expiry-reminder job handles renewal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Plan:
    """One membership plan: duration, deliveries, and price."""
    id: str
    name: str
    months: int
    deliveries: int
    price: float


PLANS: list[Plan] = [
    Plan("quarterly", "Quarterly Membership (4 prints/year)", 3, 1, 49.0),
    Plan("biannual", "Half-Year Membership (6 prints)", 6, 6, 129.0),
    Plan("annual", "Annual Membership (12 prints)", 12, 12, 239.0),
]


def get_plan(plan_id: str) -> Plan | None:
    """Look up a plan by id (None if unknown)."""
    return next((p for p in PLANS if p.id == plan_id), None)


def build_subscription_listing() -> dict:
    """Ready-to-publish Etsy listing for the membership/subscription."""
    from quoteforge.config import SHOP_NAME
    rows = "\n".join(
        f"  - {p.name}: ${p.price:.0f}" for p in PLANS)
    title = (f"Personalized Wall Art Membership | Monthly Custom Prints "
             f"Subscription Gift | {SHOP_NAME}")
    description = (
        "Give (or get) a year of meaningful, personalized wall art - a new custom "
        "piece delivered on a schedule, each one made to order.\n\n"
        "MEMBERSHIP OPTIONS\n" + rows + "\n\n"
        "HOW IT WORKS\n"
        "1. Choose a plan and tell us who it's for.\n"
        "2. You approve a free proof for each delivery before it prints.\n"
        "3. A fresh personalized piece ships on your cadence.\n\n"
        "Perfect for grandparents, long-distance family, new homes, and anyone "
        "who loves a thoughtful surprise. Cancel or pause anytime - just message us.")
    tags = ["wall art subscription", "art membership", "monthly art",
            "personalized gift", "subscription box", "custom print club",
            "gift subscription", "art of the month", "recurring gift",
            "family gift", "grandparent gift", "home decor club", "print club"]
    return {"title": title[:140], "description": description, "tags": tags[:13],
            "plans": [{"id": p.id, "name": p.name, "price": p.price} for p in PLANS]}


def start_subscription_from_order(payload: dict) -> dict:
    """If the order is a subscription, create the DB record + send a welcome email.
    Best-effort, idempotent-ish. Returns a summary."""
    plan_id = (payload.get("subscription_plan") or "").strip().lower()
    plan = get_plan(plan_id)
    email = (payload.get("customer_email") or "").strip()
    if not plan or not email:
        return {"created": False, "reason": "not a subscription order"}
    from datetime import timedelta
    end = (date.today() + timedelta(days=int(plan.months * 30.4))).isoformat()
    out = {"created": False, "plan": plan.id, "end_date": end}
    try:
        from quoteforge.db.database import add_subscription, add_subscriber, init_db
        init_db()
        out["id"] = add_subscription(email, end, payload.get("customer_name", ""),
                                     plan.id, date.today().isoformat())
        add_subscriber(email, source="subscriber", consent="yes")  # paying customer
        out["created"] = True
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    try:
        from quoteforge.config import SHOP_NAME
        from quoteforge.automation.emailer import _send_email
        from quoteforge.ai.assistant import ai_text
        name = payload.get("customer_name") or "there"
        fallback = (f"Hi {name},\n\nWelcome to the {SHOP_NAME} membership! Your "
                    f"{plan.name} is active through {end}. We'll design each piece "
                    f"and you approve a free proof before it prints. Reply anytime with who "
                    f"it's for and any details. So glad you're here!")
        body = ai_text(
            f"Write a warm 70-100 word welcome email for a new {SHOP_NAME} art "
            f"membership ({plan.name}, active through {end}) for {name}. Mention the "
            f"free proof before each print. Output only the body.",
            operation="subscription_welcome", max_tokens=240, mock=fallback)
        html = (f"<html><body style='font-family:Arial'><pre style='font-size:14px;"
                f"white-space:pre-wrap'>{body}</pre></body></html>")
        _send_email(f"Welcome to the {SHOP_NAME} membership!", html, to=email)
        out["welcomed"] = True
    except Exception:  # noqa: BLE001
        pass
    return out
