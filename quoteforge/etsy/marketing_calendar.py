"""Formal annual marketing calendar — think like a retailer, not a gift-buyer.

Buyers search WEEKS before an event, so listings must go live well ahead of the
peak and marketing starts a few weeks after that. This encodes the exact
retailer timeline (listings-live date + marketing-start date per occasion),
the revenue ranking, and the post-purchase email sequence.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SeasonPlan:
    """One season's retailer timeline: listings-live and marketing-start dates."""
    occasion: str
    listings_live: tuple[int, int]    # (month, day) — publish listings by here
    marketing_starts: tuple[int, int] # (month, day) — start ads/Pinterest here
    revenue_rank: int                 # 1 = highest revenue potential


# The retailer timeline. Listings go live early so Etsy ranking matures; the
# marketing push begins as buyers start searching.
ANNUAL_CALENDAR: list[SeasonPlan] = [
    SeasonPlan("Christmas",        (9, 15), (11, 1), 1),  # ~30-50% of annual revenue
    SeasonPlan("Mother's Day",     (3, 1),  (4, 1),  2),
    SeasonPlan("Graduation",       (3, 15), (4, 15), 3),
    SeasonPlan("Wedding Season",   (2, 1),  (4, 1),  4),
    SeasonPlan("Father's Day",     (4, 15), (5, 15), 5),
    SeasonPlan("Valentine's Day",  (12, 15),(1, 1),  6),
    SeasonPlan("Easter",           (1, 15), (2, 15), 7),
    SeasonPlan("Back to School",   (6, 1),  (7, 1),  8),
    SeasonPlan("Thanksgiving",     (9, 1),  (10, 1), 9),
    SeasonPlan("Halloween",        (8, 1),  (9, 1),  10),
]

# High-revenue categories, ranked (also year-round evergreens worth always listing)
HIGH_REVENUE_CATEGORIES = [
    "Christmas", "Mother's Day", "Graduation", "Weddings", "Father's Day",
    "Christian Gifts", "Memorial Gifts", "New Baby", "Retirement",
    "Healthcare Professionals",
]

# Post-purchase email sequence: (day_offset, message_type)
EMAIL_SEQUENCE = [
    (0,  "Thank You"),
    (14, "Review Request"),
    (30, "Upsell"),
]

# 3-year scaling targets
SCALING_TARGETS = {1: 500, 2: 2000, 3: 5000}


# ── US federal elections (every even year; Nov, alternating type) ─
# Listings go live ~10 weeks before Election Day; marketing ~6 weeks before.
ELECTION_LISTINGS_LEAD_DAYS = 70
ELECTION_MARKETING_LEAD_DAYS = 42


def election_day(year: int) -> datetime:
    """US federal Election Day: first Tuesday after the first Monday of November."""
    for day in range(2, 9):  # the Tuesday in this range follows the first Monday
        d = datetime(year, 11, day)
        if d.weekday() == 1:  # Tuesday
            return d
    raise ValueError("no election day found")  # unreachable


def next_federal_election(now: datetime | None = None) -> dict:
    """Return the next federal general election: date + type.

    Presidential every 4 years (year % 4 == 0); midterm the other even years.
    Odd years have no federal general election.
    """
    now = now or datetime.now()
    year = now.year
    if year % 2 == 1:
        year += 1  # skip odd (off) years
    elif election_day(year).date() < now.date():
        year += 2  # this year's election already passed → next even year
    etype = "Presidential Election" if year % 4 == 0 else "Midterm Election"
    eday = election_day(year)
    return {
        "year": year,
        "type": etype,
        "election_day": eday.strftime("%Y-%m-%d"),
        "is_presidential": year % 4 == 0,
    }


def election_actions(now: datetime | None = None, horizon_days: int = 45) -> list[dict]:
    """List/market triggers for the next federal election, if within horizon."""
    now = now or datetime.now()
    info = next_federal_election(now)
    eday = datetime.strptime(info["election_day"], "%Y-%m-%d")
    out = []
    triggers = [
        ("LIST LISTINGS LIVE", eday - timedelta(days=ELECTION_LISTINGS_LEAD_DAYS)),
        ("START MARKETING", eday - timedelta(days=ELECTION_MARKETING_LEAD_DAYS)),
    ]
    for label, when in triggers:
        days = (when.date() - now.date()).days
        if days <= horizon_days:
            out.append({
                "occasion": info["type"],
                "action": label,
                "date": when.strftime("%Y-%m-%d"),
                "days_away": days,
                "revenue_rank": 6,  # civic season ~ mid-tier, spikes every even year
                "urgency": ("OVERDUE" if days < 0 else
                            "THIS WEEK" if days <= 7 else "Upcoming"),
            })
    return out


def _next_date(month: int, day: int, now: datetime) -> datetime:
    """The next occurrence of (month, day) on or after `now` (rolls to next year)."""
    candidate = datetime(now.year, month, day)
    if candidate.date() < now.date():
        candidate = datetime(now.year + 1, month, day)
    return candidate


def upcoming_actions(now: datetime | None = None, horizon_days: int = 45) -> list[dict]:
    """What listing/marketing actions are due soon, soonest first.

    Surfaces each season's 'list now' and 'start marketing' triggers that fall
    within the horizon (or are overdue), so you act 4-8 weeks early.
    """
    now = now or datetime.now()
    actions: list[dict] = []
    for s in ANNUAL_CALENDAR:
        live = _next_date(*s.listings_live, now)
        mkt = _next_date(*s.marketing_starts, now)
        for label, when in (("LIST LISTINGS LIVE", live), ("START MARKETING", mkt)):
            days = (when.date() - now.date()).days
            if days <= horizon_days:
                actions.append({
                    "occasion": s.occasion,
                    "action": label,
                    "date": when.strftime("%Y-%m-%d"),
                    "days_away": days,
                    "revenue_rank": s.revenue_rank,
                    "urgency": ("OVERDUE" if days < 0 else
                                "THIS WEEK" if days <= 7 else "Upcoming"),
                })
    # Federal elections (every even year) — civic poster season
    actions.extend(election_actions(now, horizon_days))
    actions.sort(key=lambda a: (a["days_away"], a["revenue_rank"]))
    return actions


def due_email_touch(order_created_at: str, now: datetime | None = None) -> str | None:
    """Which post-purchase email is due for an order today (Day 0/14/30)?"""
    now = now or datetime.now()
    try:
        created = datetime.fromisoformat((order_created_at or "").replace("Z", ""))
    except ValueError:
        return None
    age = (now.date() - created.date()).days
    due = None
    for offset, msg_type in EMAIL_SEQUENCE:
        if age >= offset:
            due = msg_type
    return due  # the latest milestone reached


def calendar_summary() -> dict:
    """Snapshot of the calendar: season count, top seasons, emails, targets."""
    return {
        "seasons": len(ANNUAL_CALENDAR),
        "top_revenue": [s.occasion for s in
                        sorted(ANNUAL_CALENDAR, key=lambda x: x.revenue_rank)[:3]],
        "email_sequence": EMAIL_SEQUENCE,
        "scaling_targets": SCALING_TARGETS,
    }
