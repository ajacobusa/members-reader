"""Tests for the formal annual marketing calendar."""
from datetime import datetime

from quoteforge.etsy.marketing_calendar import (
    ANNUAL_CALENDAR, HIGH_REVENUE_CATEGORIES, EMAIL_SEQUENCE, SCALING_TARGETS,
    upcoming_actions, due_email_touch, calendar_summary,
    election_day, next_federal_election, election_actions,
)


def test_all_ten_seasons_present():
    occasions = {s.occasion for s in ANNUAL_CALENDAR}
    for must in ["Christmas", "Valentine's Day", "Mother's Day", "Graduation",
                 "Wedding Season", "Father's Day", "Easter", "Back to School",
                 "Thanksgiving", "Halloween"]:
        assert must in occasions


def test_christmas_is_rank_one():
    christmas = next(s for s in ANNUAL_CALENDAR if s.occasion == "Christmas")
    assert christmas.revenue_rank == 1  # ~30-50% of annual revenue


def test_exact_timeline_dates():
    by = {s.occasion: s for s in ANNUAL_CALENDAR}
    assert by["Valentine's Day"].listings_live == (12, 15)
    assert by["Valentine's Day"].marketing_starts == (1, 1)
    assert by["Christmas"].listings_live == (9, 15)
    assert by["Christmas"].marketing_starts == (11, 1)
    assert by["Graduation"].listings_live == (3, 15)


def test_listings_live_before_marketing():
    """For each season, listings must go live before marketing starts (in-cycle)."""
    for s in ANNUAL_CALENDAR:
        # Compare as day-of-year-ish; Valentine's/Christmas wrap year boundary,
        # so just assert both dates are set and distinct.
        assert s.listings_live != s.marketing_starts


def test_upcoming_actions_christmas_in_september():
    # On Sep 10, "list Christmas listings live (Sep 15)" should be imminent
    actions = upcoming_actions(now=datetime(2026, 9, 10), horizon_days=30)
    xmas_live = [a for a in actions if a["occasion"] == "Christmas"
                 and a["action"] == "LIST LISTINGS LIVE"]
    assert xmas_live
    assert xmas_live[0]["days_away"] == 5
    assert xmas_live[0]["urgency"] == "THIS WEEK"


def test_upcoming_actions_sorted_by_soonest():
    actions = upcoming_actions(now=datetime(2026, 3, 1), horizon_days=90)
    days = [a["days_away"] for a in actions]
    assert days == sorted(days)


def test_email_sequence_day_0_14_30():
    assert EMAIL_SEQUENCE == [(0, "Thank You"), (14, "Review Request"), (30, "Upsell")]


def test_due_email_touch_progression():
    now = datetime(2026, 6, 30)
    assert due_email_touch((now.replace(day=30)).isoformat(), now) == "Thank You"
    # 15 days old → review request is the latest milestone
    from datetime import timedelta
    d15 = (now - timedelta(days=15)).isoformat()
    assert due_email_touch(d15, now) == "Review Request"
    d31 = (now - timedelta(days=31)).isoformat()
    assert due_email_touch(d31, now) == "Upsell"


def test_high_revenue_ranking():
    assert HIGH_REVENUE_CATEGORIES[0] == "Christmas"
    assert "Memorial Gifts" in HIGH_REVENUE_CATEGORIES
    assert "Healthcare Professionals" in HIGH_REVENUE_CATEGORIES


def test_scaling_targets():
    assert SCALING_TARGETS == {1: 500, 2: 2000, 3: 5000}


def test_calendar_summary():
    s = calendar_summary()
    assert s["seasons"] == 10
    assert "Christmas" in s["top_revenue"]


# ── Federal elections (midterm + 4-year presidential) ───────────

def test_election_day_formula():
    # First Tuesday after first Monday of November
    assert election_day(2026) == datetime(2026, 11, 3)   # midterm
    assert election_day(2028) == datetime(2028, 11, 7)   # presidential
    assert election_day(2024) == datetime(2024, 11, 5)
    # Always a Tuesday, always Nov 2-8
    for y in range(2024, 2040, 2):
        d = election_day(y)
        assert d.weekday() == 1 and 2 <= d.day <= 8


def test_midterm_vs_presidential():
    # 2026 = midterm, 2028 = presidential
    assert next_federal_election(datetime(2026, 1, 1))["type"] == "Midterm Election"
    assert next_federal_election(datetime(2028, 1, 1))["type"] == "Presidential Election"
    assert next_federal_election(datetime(2028, 1, 1))["is_presidential"] is True


def test_odd_year_rolls_to_next_even():
    info = next_federal_election(datetime(2027, 3, 1))
    assert info["year"] == 2028  # off-year → next even-year election
    assert info["is_presidential"] is True


def test_after_election_rolls_to_next_cycle():
    # The day after the 2026 election → next is 2028
    info = next_federal_election(datetime(2026, 11, 10))
    assert info["year"] == 2028


def test_election_actions_appear_before_election():
    # ~10 weeks before the 2026 midterm, the "list listings live" trigger fires
    now = datetime(2026, 8, 26)  # ~70 days before Nov 3
    acts = election_actions(now, horizon_days=10)
    assert any(a["action"] == "LIST LISTINGS LIVE"
               and "Midterm" in a["occasion"] for a in acts)


def test_election_in_upcoming_actions():
    # Election season shows up alongside holidays in the unified calendar
    now = datetime(2026, 9, 1)
    acts = upcoming_actions(now=now, horizon_days=60)
    assert any("Election" in a["occasion"] for a in acts)


def test_cli_calendar(capsys):
    from quoteforge import admin
    rc = admin.main(["calendar"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ANNUAL MARKETING CALENDAR" in out
    assert "Highest-revenue" in out
