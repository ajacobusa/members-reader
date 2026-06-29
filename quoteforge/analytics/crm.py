"""CRM Dashboard - a single 360 view per customer, from real data only.

Joins everything we know about a customer by email: orders, lifetime value, gift
profiles, subscriptions, support messages, reviews, and reward/referral points.
Useful once you pass ~100 customers. Nothing is invented - empty sections stay
empty.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _all_orders():
    """All orders from the DB (initializes the schema first)."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    return get_all_orders(limit=100000)


def _key(o: dict) -> str:
    """Normalized customer key for an order: email, falling back to name."""
    return (o.get("customer_email") or o.get("customer_name") or "").strip().lower()


def customer_list(orders: list[dict] | None = None) -> list[dict]:
    """Summary row per customer (orders, revenue, last order), best customers first."""
    rows = _all_orders() if orders is None else orders
    agg: dict[str, dict] = {}
    for o in rows:
        k = _key(o)
        if not k:
            continue
        try:
            rev = float(o.get("sale_price") or 0.0)
        except (TypeError, ValueError):
            rev = 0.0
        a = agg.setdefault(k, {"key": k, "name": o.get("customer_name") or "",
                               "email": o.get("customer_email") or "",
                               "orders": 0, "revenue": 0.0, "last_order": ""})
        a["orders"] += 1
        a["revenue"] = round(a["revenue"] + rev, 2)
        ca = o.get("created_at") or ""
        if ca > a["last_order"]:
            a["last_order"] = ca
    return sorted(agg.values(), key=lambda a: a["revenue"], reverse=True)


def customer_360(email: str) -> dict:
    """Everything we know about one customer, joined by email."""
    from quoteforge.db.database import (init_db, get_gift_profiles,
                                        get_subscriptions, get_customer_messages,
                                        get_published_reviews, get_rewards)
    init_db()
    email = (email or "").strip().lower()
    orders = [o for o in _all_orders() if _key(o) == email]
    names = {(o.get("customer_name") or "").strip().lower()
             for o in orders if o.get("customer_name")}

    revenue = round(sum(float(o.get("sale_price") or 0) for o in orders), 2)
    order_ids = [o.get("order_id") for o in orders if o.get("order_id")]
    support = []
    for oid in order_ids:
        try:
            support.extend(get_customer_messages(oid))
        except Exception as exc:  # noqa: BLE001 - a missing message thread is skipped
            logger.debug("support messages skipped for order %s: %s", oid, exc)
    # reviews tie by customer name (reviews aren't keyed by email)
    reviews = [r for r in get_published_reviews(200)
               if (r.get("customer_name") or "").strip().lower() in names]
    subs = [s for s in get_subscriptions()
            if (s.get("customer_email") or "").strip().lower() == email]
    profiles = get_gift_profiles(email)
    rewards = get_rewards(email)
    points = sum(int(r.get("points") or 0) for r in rewards)

    return {
        "email": email,
        "name": orders[0].get("customer_name") if orders else "",
        "orders": orders, "order_count": len(orders), "revenue": revenue,
        "aov": round(revenue / len(orders), 2) if orders else 0.0,
        "gift_profiles": profiles, "subscriptions": subs,
        "support_messages": support, "reviews": reviews,
        "reward_points": points, "rewards": rewards,
        "is_repeat": len(orders) >= 2,
    }


def format_customer_text(email: str) -> str:
    """Plain-text 360 profile for one customer, keyed by email."""
    c = customer_360(email)
    if not c["orders"] and not c["gift_profiles"] and not c["subscriptions"]:
        return (f"CRM - {email}\n" + "-" * 40 +
                "\nNo records found for this customer yet.")
    lines = [f"CRM 360 - {c['name'] or c['email']} <{c['email']}>", "-" * 48,
             f"  Orders        : {c['order_count']}  "
             f"(revenue ${c['revenue']:,.2f}, AOV ${c['aov']:,.2f})",
             f"  Repeat buyer  : {'yes' if c['is_repeat'] else 'no'}",
             f"  Reward points : {c['reward_points']}",
             f"  Gift profiles : {len(c['gift_profiles'])}",
             f"  Subscriptions : {len(c['subscriptions'])}",
             f"  Reviews       : {len(c['reviews'])}",
             f"  Support msgs  : {len(c['support_messages'])}"]
    if c["gift_profiles"]:
        lines.append("  Saved recipients:")
        for p in c["gift_profiles"][:8]:
            lines.append(f"     {p.get('recipient_name','')} "
                         f"({p.get('relationship','')}) - {p.get('occasion','')}")
    return "\n".join(lines)


def format_crm_overview(top: int = 20) -> str:
    """Plain-text table of the top customers by revenue."""
    rows = customer_list()
    if not rows:
        return ("CRM overview\n" + "-" * 40 +
                "\nNo customers yet - this populates after your first orders.")
    lines = ["CRM overview (top customers)", "-" * 48,
             "  Rank  Customer                     Orders   Revenue"]
    for i, r in enumerate(rows[:top], 1):
        who = (r["name"] or r["email"])[:26]
        lines.append(f"  {i:>3}.  {who:<26} {r['orders']:>5}   "
                     f"${r['revenue']:,.2f}")
    return "\n".join(lines)
