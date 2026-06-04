"""Automated sales & upsell engine.

Decides — automatically — WHAT to offer, to WHOM, and WHEN, to maximize revenue
per customer. It produces a daily "actions to send" digest: post-purchase
upsells, review requests, repeat-buyer win-backs, plus best-seller analytics
telling you what to make more of.

Boundary: Etsy provides no API for new shops to auto-send messages, so YOU paste
each suggested message into the Etsy conversation. The engine removes all the
thinking — it tells you exactly what to send, to whom, and the wording.
"""
from datetime import datetime, timedelta

# Occasions that recur every year → prime win-back / repeat-purchase targets
RECURRING_OCCASIONS = ("anniversary", "birthday", "mother", "father",
                       "valentine", "christmas")

# A small next-order incentive that lifts repeat purchases
NEXT_ORDER_COUPON = "THANKYOU10"  # 10% off next order (create this code in Etsy)


def best_sellers(orders: list[dict], top_n: int = 5) -> dict:
    """Identify what's selling so you can double down (make more of it)."""
    by_occasion: dict[str, int] = {}
    by_relationship: dict[str, int] = {}
    billable = {"in_production", "shipped", "delivered",
                "approved_ready_to_print", "awaiting_customer_approval"}
    for o in orders:
        if o.get("status") not in billable:
            continue
        occ = o.get("occasion", "") or "Unknown"
        rel = o.get("relationship", "") or "Unknown"
        by_occasion[occ] = by_occasion.get(occ, 0) + 1
        by_relationship[rel] = by_relationship.get(rel, 0) + 1

    def _top(d):
        return sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    return {
        "top_occasions": _top(by_occasion),
        "top_relationships": _top(by_relationship),
    }


def upsell_actions(orders: list[dict]) -> list[dict]:
    """Orders that should get a post-purchase upsell offer (canvas/framed/bundle).

    Targets fulfilled orders that haven't been offered an upsell yet.
    """
    from quoteforge.etsy.product_lines import story_to_products
    eligible = {"approved_ready_to_print", "in_production", "shipped"}
    actions = []
    for o in orders:
        if o.get("status") in eligible and not o.get("upsell_sent"):
            # Cross-sell: the SAME message on 2-3 other products (mug, journal...)
            extras = [p["product"] for p in story_to_products(o.get("occasion", ""))
                      if p["product"] not in ("Poster 18x24",)][:3]
            suggest = ("Offer the same design as a matching set: "
                       + ", ".join(extras) + ".") if extras else \
                      "Offer the matching canvas/framed upgrade."
            actions.append({
                "type": "upsell",
                "order_id": o["order_id"],
                "customer": o.get("sender_name") or o.get("customer_name") or "there",
                "occasion": o.get("occasion", ""),
                "suggested": suggest,
                "cross_sell_products": extras,
            })
    return actions


def review_actions(now: datetime | None = None) -> list[dict]:
    """Review requests that are due to send (scheduled date reached)."""
    from quoteforge.db.database import get_pending_reviews
    now = now or datetime.now()
    actions = []
    for r in get_pending_reviews():
        sched = r.get("scheduled_for", "") or ""
        try:
            due = datetime.fromisoformat(sched)
        except ValueError:
            due = now  # if unset, treat as due
        if due <= now:
            actions.append({
                "type": "review",
                "order_id": r["order_id"],
                "message": r["review_message"],
            })
    return actions


def winback_actions(orders: list[dict], now: datetime | None = None) -> list[dict]:
    """Repeat-purchase win-backs: customers who bought a recurring-occasion gift
    ~11-12 months ago — remind them the date is coming up again.
    """
    now = now or datetime.now()
    actions = []
    for o in orders:
        occ = (o.get("occasion", "") or "").lower()
        if not any(k in occ for k in RECURRING_OCCASIONS):
            continue
        created = o.get("created_at", "") or ""
        try:
            dt = datetime.fromisoformat(created.replace("Z", ""))
        except ValueError:
            continue
        age_days = (now - dt).days
        if 330 <= age_days <= 400:  # roughly a year later
            actions.append({
                "type": "winback",
                "order_id": o["order_id"],
                "customer": o.get("sender_name") or o.get("customer_name") or "there",
                "occasion": o.get("occasion", ""),
                "suggested": (f"It's almost a year since their {o.get('occasion','')} "
                              f"order — offer a fresh design for this year, plus "
                              f"coupon {NEXT_ORDER_COUPON}."),
            })
    return actions


def sales_actions_digest(now: datetime | None = None) -> dict:
    """The full 'what to send today to make more money' digest."""
    from quoteforge.db.database import get_all_orders
    now = now or datetime.now()
    orders = get_all_orders(limit=1000000)
    upsells = upsell_actions(orders)
    reviews = review_actions(now)
    winbacks = winback_actions(orders, now)
    return {
        "timestamp": now.isoformat(),
        "upsells": upsells,
        "reviews": reviews,
        "winbacks": winbacks,
        "best_sellers": best_sellers(orders),
        "total_actions": len(upsells) + len(reviews) + len(winbacks),
        "next_order_coupon": NEXT_ORDER_COUPON,
    }


def format_digest_text(digest: dict) -> str:
    lines = ["=" * 52, "AUTOMATED SALES ACTIONS — send these to make more $",
             "=" * 52]
    lines.append(f"\nUPSELLS TO SEND ({len(digest['upsells'])}):")
    for a in digest["upsells"] or [{"order_id": "—", "customer": "", "suggested": "none"}]:
        lines.append(f"  • {a['order_id']} ({a.get('customer','')}): {a['suggested']}")
    lines.append(f"\nREVIEW REQUESTS DUE ({len(digest['reviews'])}):")
    for a in digest["reviews"] or [{"order_id": "—"}]:
        lines.append(f"  • {a['order_id']}")
    lines.append(f"\nREPEAT-BUYER WIN-BACKS ({len(digest['winbacks'])}):")
    for a in digest["winbacks"] or [{"order_id": "—", "suggested": "none"}]:
        lines.append(f"  • {a.get('order_id','—')}: {a.get('suggested','')}")
    bs = digest["best_sellers"]
    lines.append("\nBEST SELLERS (make more of these):")
    lines.append(f"  Top occasions   : {bs['top_occasions']}")
    lines.append(f"  Top relationships: {bs['top_relationships']}")
    lines.append("=" * 52)
    return "\n".join(lines)
