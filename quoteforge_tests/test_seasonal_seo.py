"""Tests for the demand-driven, calendar-aware SEO agent."""
from datetime import datetime
from unittest.mock import patch

from quoteforge.etsy.seasonal_seo import (
    seasonal_seo_plan, format_seasonal_seo, _phase, SEASON_SEO, send_seasonal_seo,
)
from quoteforge import admin


def test_refresh_window_fires_4_weeks_out():
    # ~4 weeks before a peak -> SEO REFRESH (Etsy needs time to re-rank).
    assert _phase(28) == "SEO REFRESH"
    assert _phase(35) == "SEO REFRESH"


def test_lastminute_window_fires_1_week_out():
    assert _phase(7) == "LAST-MINUTE PUSH"
    assert _phase(5) == "LAST-MINUTE PUSH"


def test_no_phase_outside_windows():
    assert _phase(60) == ""   # too far
    assert _phase(15) == ""   # between windows
    assert _phase(1) == ""    # too late


def test_mothers_day_refresh_one_month_before():
    # April 13 -> ~28 days before May 11 Mother's Day -> refresh due.
    now = datetime(2026, 4, 13)
    plan = seasonal_seo_plan(now)
    md = [e for e in plan["due"] if e["season"] == "Mother's Day"]
    assert md and md[0]["phase"] == "SEO REFRESH"
    assert any("mom" in k for k in md[0]["keywords"])


def test_lastminute_week_before():
    # May 5 -> ~6 days before Mother's Day -> last-minute push.
    now = datetime(2026, 5, 5)
    plan = seasonal_seo_plan(now)
    md = [e for e in plan["due"] if e["season"] == "Mother's Day"]
    assert md and md[0]["phase"] == "LAST-MINUTE PUSH"


def test_far_seasons_are_deprioritized():
    now = datetime(2026, 7, 1)  # mid-summer, Christmas far away
    plan = seasonal_seo_plan(now)
    assert any("Christmas" in d for d in plan["deprioritize"])


def test_due_actions_demand_ranked():
    now = datetime(2026, 4, 13)
    plan = seasonal_seo_plan(now)
    # nearest peak first, then by revenue rank
    days = [e["days_to_peak"] for e in plan["due"]]
    assert days == sorted(days)


def test_graduation_targets_professions():
    now = datetime(2026, 4, 20)  # ~30 days before May 20 graduation
    plan = seasonal_seo_plan(now)
    grad = [e for e in plan["due"] if e["season"] == "Graduation"]
    assert grad and any("profession" in t for t in grad[0]["targets"])


def test_format_text():
    plan = seasonal_seo_plan(datetime(2026, 4, 13))
    text = format_seasonal_seo(plan)
    assert "DEMAND-DRIVEN SEO PLAN" in text


def test_send_skips_when_no_action():
    # A date with nothing in either window emails nothing.
    now = datetime(2026, 7, 20)
    out = send_seasonal_seo(now)
    assert out["status"] == "no_action"


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_seasonal_seo(capsys):
    rc = admin.main(["seasonal-seo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DEMAND-DRIVEN SEO PLAN" in out
