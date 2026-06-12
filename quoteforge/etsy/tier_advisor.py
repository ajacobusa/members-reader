"""Demand-based tier recommendations.

Watches monthly order volume and flags when you're approaching a service's
plan limit so you can upgrade BEFORE you hit it. Does NOT auto-purchase —
upgrading a paid plan is your decision; this just tells you when it's time.
"""
from dataclasses import dataclass


@dataclass
class TierRule:
    """One service plan's capacity and the upgrade path beyond it."""
    service: str
    plan: str
    monthly_limit: int       # orders/images this plan comfortably supports
    monthly_cost: float
    next_plan: str
    next_cost: float


# Ordered low → high. Bannerbear credits = images; assume ~1 image/order here.
TIER_LADDER: list[TierRule] = [
    TierRule("Bannerbear", "Free trial", 30, 0.0, "Automate", 49.0),
    TierRule("Bannerbear", "Automate", 1000, 49.0, "Scale", 149.0),
    TierRule("Bannerbear", "Scale", 10000, 149.0, "Enterprise", 299.0),
    TierRule("Make.com", "Starter (10k ops)", 1200, 9.0, "Core", 16.0),
    TierRule("Make.com", "Core (10k ops)", 1200, 16.0, "Pro", 29.0),
]

# Fraction of a plan's limit at which we warn (upgrade before hitting the wall)
WARN_THRESHOLD = 0.8


def recommend_tiers(monthly_orders: int, renderer: str = "local") -> list[dict]:
    """Return upgrade recommendations triggered by current monthly order volume.

    Only services actually in use are evaluated:
    - Bannerbear rules apply only when renderer == "bannerbear".
    - Make.com rules always apply if you use the webhook automation.
    """
    recs: list[dict] = []
    for rule in TIER_LADDER:
        if rule.service == "Bannerbear" and renderer != "bannerbear":
            continue
        # Each order ~ a few Make.com operations; approximate ops = orders * 4
        usage = monthly_orders * 4 if rule.service == "Make.com" else monthly_orders
        if usage >= rule.monthly_limit:
            recs.append({
                "service": rule.service,
                "current_plan": rule.plan,
                "status": "OVER_LIMIT",
                "message": (f"{rule.service}: {usage} exceeds {rule.plan} limit "
                            f"({rule.monthly_limit}). Upgrade to {rule.next_plan} "
                            f"(${rule.next_cost}/mo)."),
                "recommended_plan": rule.next_plan,
                "recommended_cost": rule.next_cost,
            })
        elif usage >= rule.monthly_limit * WARN_THRESHOLD:
            recs.append({
                "service": rule.service,
                "current_plan": rule.plan,
                "status": "APPROACHING",
                "message": (f"{rule.service}: {usage} is at "
                            f"{round(usage / rule.monthly_limit * 100)}% of the "
                            f"{rule.plan} limit. Plan to upgrade to {rule.next_plan} soon."),
                "recommended_plan": rule.next_plan,
                "recommended_cost": rule.next_cost,
            })
    return recs
