"""Tests for the year-round occasion taxonomy + monthly planner."""
from datetime import datetime

from quoteforge.etsy.occasions import (
    MONTHLY_OCCASIONS, RELIGIOUS_OCCASIONS, EMOTIONAL_EVENTS, PROFESSIONS,
    RELATIONSHIPS, EVERGREEN_CATEGORIES, FAMILY_MILESTONES, EDUCATION_MILESTONES,
    get_month_occasions, get_current_month_plan, all_occasions, occasion_count,
    coverage_summary,
)


def test_all_twelve_months_covered():
    assert len(MONTHLY_OCCASIONS) == 12
    for m in ["January", "February", "December"]:
        assert m in MONTHLY_OCCASIONS
        assert len(MONTHLY_OCCASIONS[m]) >= 3


def test_four_religions_covered():
    for rel in ["Christian", "Jewish", "Hindu", "Muslim"]:
        assert rel in RELIGIOUS_OCCASIONS
        assert len(RELIGIOUS_OCCASIONS[rel]) >= 3


def test_key_occasions_present():
    occ = set(all_occasions())
    # Spot-check critical high-margin and seasonal occasions
    for must_have in ["Valentine's Day", "Mother's Day", "Father's Day",
                      "Easter", "Christmas", "Hanukkah", "Diwali", "Ramadan",
                      "Pet Memorial", "Loss Of Parent", "Cancer Survivor",
                      "Bar Mitzvah", "Quinceañera", "Sweet 16", "PhD"]:
        assert must_have in occ, f"Missing occasion: {must_have}"


def test_emotional_events_high_margin_set():
    # The auditor's note: emotional events are the highest-margin — must exist
    for e in ["Loss Of Child", "Loss Of Spouse", "Sobriety Milestone",
              "Grief Support", "Infertility Journey"]:
        assert e in EMOTIONAL_EVENTS


def test_professions_include_healthcare():
    for p in ["Dentist", "Nurse", "Physician", "Teacher", "Firefighter"]:
        assert p in PROFESSIONS


def test_relationships_complete():
    for r in ["Daughter", "Son", "Grandmother", "Godfather", "Best Friend"]:
        assert r in RELATIONSHIPS


def test_evergreen_categories():
    assert "Christian Personalized Gifts" in EVERGREEN_CATEGORIES
    assert "Memorial Gifts" in EVERGREEN_CATEGORIES
    assert len(EVERGREEN_CATEGORIES) >= 10


def test_birthday_milestones_full_range():
    for b in ["First Birthday", "18th Birthday", "50th Birthday", "100th Birthday"]:
        assert b in FAMILY_MILESTONES


def test_education_milestones():
    for e in ["High School Graduation", "PhD", "Medical School", "Nursing School"]:
        assert e in EDUCATION_MILESTONES


def test_get_month_by_number_and_name():
    feb_num = get_month_occasions(2)
    feb_name = get_month_occasions("February")
    assert feb_num == feb_name
    assert "Valentine's Day" in feb_num


def test_current_month_plan_structure():
    plan = get_current_month_plan(datetime(2026, 5, 1))
    assert plan["month"] == "May"
    assert "Mother's Day" in plan["this_month"]
    assert plan["prep_next_month"] == "June"
    assert "Father's Day" in plan["next_month"]  # prep ahead
    assert len(plan["evergreen_always_list"]) >= 10


def test_december_wraps_to_january_prep():
    plan = get_current_month_plan(datetime(2026, 12, 15))
    assert plan["month"] == "December"
    assert plan["prep_next_month"] == "January"
    assert "New Year's Day" in plan["next_month"]


def test_occasion_count_is_large():
    # Year-round coverage should be well over 100 distinct occasions
    assert occasion_count() >= 120


def test_coverage_summary():
    cov = coverage_summary()
    assert cov["total_distinct_occasions"] >= 120
    assert cov["calendar_months"] > 0
    assert cov["emotional_events"] >= 10


def test_generator_occasions_includes_new_ones():
    from quoteforge.quotes.generator import OCCASIONS
    occ = set(OCCASIONS)
    # The expanded generator list should now carry the full taxonomy
    assert "Diwali" in occ
    assert "Pet Memorial" in occ
    assert "Quinceañera" in occ
    assert len(OCCASIONS) >= 100


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_plan(capsys):
    from quoteforge import admin
    rc = admin.main(["plan"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OCCASION PLAN" in out
    assert "CREATE THESE NOW" in out
    assert "PREP AHEAD" in out
    assert "evergreen" in out.lower()
