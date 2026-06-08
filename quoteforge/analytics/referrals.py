"""Referral & loyalty leaderboard - rewards referrals, repeat purchases, reviews.

Points come from two real sources:
  1. Explicitly recorded events in the `rewards` ledger (referrals you confirm,
     reviews you credit) via record_*().
  2. Repeat purchases DERIVED from real orders (a customer's 2nd+ order earns
     repeat points) - computed on the fly, idempotently mirrored into the ledger.

The leaderboard ranks customers by total points. No fabricated activity.
"""
from __future__ import annotations

# Points per event (tune as the program matures).
POINTS = {"referral": 50, "review": 20, "repeat_purchase": 30}


def record_referral(referrer_email: str, referee_email: str = "") -> int:
    """Credit a confirmed referral. Idempotent per (referrer, referee)."""
    from quoteforge.db.database import add_reward
    return add_reward(referrer_email, "referral", POINTS["referral"],
                      ref=(referee_email or "").strip().lower(),
                      note="referral")


def record_review_credit(email: str, review_ref: str = "") -> int:
    """Credit a customer for leaving a (real) review. Idempotent per review_ref."""
    from quoteforge.db.database import add_reward
    return add_reward(email, "review", POINTS["review"], ref=review_ref,
                      note="review credit")


def sync_repeat_purchase_points(orders: list[dict] | None = None) -> int:
    """Award repeat-purchase points for each customer's 2nd+ confirmed order.

    Idempotent: keyed by order_id in the rewards ledger, so re-running is safe.
    Returns the number of NEW reward rows created.
    """
    from quoteforge.db.database import init_db, get_all_orders, add_reward
    init_db()
    rows = get_all_orders(limit=100000) if orders is None else orders
    # confirmed sales, oldest first, grouped per customer
    by_cust: dict[str, list[dict]] = {}
    for o in sorted(rows, key=lambda x: x.get("created_at") or ""):
        if o.get("sale_price") in (None, 0):
            continue
        email = (o.get("customer_email") or "").strip().lower()
        if "@" not in email:
            continue
        by_cust.setdefault(email, []).append(o)
    created = 0
    for email, cust_orders in by_cust.items():
        for o in cust_orders[1:]:                       # skip the first (not repeat)
            if add_reward(email, "repeat_purchase", POINTS["repeat_purchase"],
                          ref=o.get("order_id", ""), note="repeat purchase"):
                created += 1
    return created


def leaderboard(top: int = 20, sync_repeats: bool = True) -> list[dict]:
    """Customers ranked by total reward points, with a per-kind breakdown."""
    from quoteforge.db.database import init_db, get_rewards
    init_db()
    if sync_repeats:
        sync_repeat_purchase_points()
    agg: dict[str, dict] = {}
    for r in get_rewards():
        email = r["email"]
        a = agg.setdefault(email, {"email": email, "points": 0,
                                   "referral": 0, "review": 0,
                                   "repeat_purchase": 0, "events": 0})
        a["points"] += int(r.get("points") or 0)
        a["events"] += 1
        kind = r.get("kind")
        if kind in a:
            a[kind] += int(r.get("points") or 0)
    ranked = sorted(agg.values(), key=lambda a: a["points"], reverse=True)
    return ranked[:top]


def format_leaderboard_text(top: int = 20) -> str:
    rows = leaderboard(top)
    if not rows:
        return ("Referral & loyalty leaderboard\n" + "-" * 44 +
                "\nNo reward activity yet - points accrue from referrals, repeat "
                "purchases, and credited reviews.")
    lines = ["Referral & loyalty leaderboard", "-" * 44,
             "  Rank  Customer                     Pts  (ref/rev/repeat)"]
    for i, r in enumerate(rows, 1):
        lines.append(f"  {i:>3}.  {r['email'][:26]:<26} {r['points']:>5}  "
                     f"({r['referral']}/{r['review']}/{r['repeat_purchase']})")
    return "\n".join(lines)
