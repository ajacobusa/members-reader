"""Tests for the Etsy + Gelato policy engine and policy-aware escalation."""
from unittest.mock import patch

import pytest

from quoteforge.etsy.policy import (
    POLICIES, policy_for, policy_facts, format_policy_text,
)
from quoteforge.automation.autopilot import decide
from quoteforge import admin


# ── Policy correctness vs. Etsy/Gelato reality ───────────────────

def test_personalized_remorse_not_returnable_and_uncovered():
    for cat in ["changed_mind", "wrong_personalization",
                "approved_then_changed_mind"]:
        p = policy_for(cat)
        assert p.etsy_returnable is False
        assert p.gelato_covered is False
        assert p.etsy_protection_risk is False  # genuine buyer's remorse


def test_defect_and_damage_gelato_covered_with_protection_risk():
    for cat in ["damaged_package", "printing_error", "poor_quality",
                "lost_package"]:
        p = policy_for(cat)
        assert p.gelato_covered is True
        assert p.etsy_protection_risk is True  # Etsy can force a refund
        assert p.report_window_days > 0


def test_wrong_address_not_covered():
    p = policy_for("wrong_address")
    assert p.gelato_covered is False
    assert p.etsy_returnable is False


def test_defect_window_matches_config():
    from quoteforge.config import POLICY_DEFECT_WINDOW_DAYS, POLICY_LOST_WINDOW_DAYS
    assert policy_for("damaged_package").report_window_days == POLICY_DEFECT_WINDOW_DAYS
    assert policy_for("lost_package").report_window_days == POLICY_LOST_WINDOW_DAYS


def test_policy_facts_unknown_category():
    f = policy_facts("banana")
    assert f["known"] is False


def test_format_policy_text():
    t = format_policy_text("damaged_package")
    assert "Gelato covers reprint : yes" in t
    assert "Report window" in t


# ── Policy rides along with money-back escalation ────────────────

def test_refund_escalation_carries_policy():
    d = decide("my print is damaged and I want a refund")
    assert d.auto is False
    assert d.policy.get("known") is True
    assert d.policy["gelato_covered"] is True
    assert "replacement" in d.policy["recommended"].lower()


def test_auto_decision_also_has_policy():
    d = decide("the frame arrived cracked")  # auto replacement
    assert d.auto is True
    assert d.policy["category"] == "damaged_package"


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_policy_single(capsys):
    rc = admin.main(["policy", "damaged_package"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "POLICY" in out and "Gelato covers reprint" in out


def test_cli_policy_all(capsys):
    rc = admin.main(["policy"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "changed_mind" in out and "cancellation" in out
