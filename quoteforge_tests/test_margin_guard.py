"""Tests for the margin-floor guard."""
from quoteforge.etsy.margin_guard import (
    margin_check, min_price_for_margin, audit_catalog, format_audit_text,
)
from quoteforge import admin


def test_margin_check_pass():
    # $30 poster on $11 cost clears a 50% floor.
    c = margin_check(29.99, 11.0, floor_pct=50)
    assert c["ok"] is True
    assert c["shortfall_pct"] == 0.0


def test_margin_check_fail_reports_min_price():
    # A thin-margin item fails and reports the price that would fix it.
    c = margin_check(54.99, 28.0, floor_pct=50)
    assert c["ok"] is False
    assert c["shortfall_pct"] > 0
    # Pricing at the suggested minimum should then clear the floor.
    fixed = margin_check(c["min_price_for_floor"], 28.0, floor_pct=50)
    assert fixed["margin_pct"] >= 50


def test_min_price_monotonic_in_cost():
    assert min_price_for_margin(20.0, 50) > min_price_for_margin(10.0, 50)


def test_impossible_floor_returns_inf():
    # A floor above (1 - fees) can never be met.
    assert min_price_for_margin(10.0, 95) == float("inf")


def test_entire_catalog_clears_60pct_floor():
    # Hard guarantee: every product AND gallery set nets at least 60%.
    audit = audit_catalog(floor_pct=60)
    assert audit["below_floor"] == 0, (
        "Below 60%: " + ", ".join(
            f"{o['name']} ({o['margin_pct']}%)" for o in audit["offenders"]))


def test_default_floor_is_60():
    from quoteforge.config import TARGET_MARGIN_PCT
    assert TARGET_MARGIN_PCT == 60


def test_audit_catalog_runs_over_products_and_sets():
    audit = audit_catalog(floor_pct=50)
    assert audit["checked"] > 0
    # offenders is a subset, sorted worst-first
    if audit["offenders"]:
        margins = [o["margin_pct"] for o in audit["offenders"]]
        assert margins == sorted(margins)


def test_audit_clean_at_low_floor():
    # At a very low floor, nothing is below it.
    audit = audit_catalog(floor_pct=5)
    assert audit["below_floor"] == 0
    assert "[OK]" in format_audit_text(audit)


def test_format_audit_flags_offenders():
    audit = audit_catalog(floor_pct=70)  # high floor -> guaranteed offenders
    text = format_audit_text(audit)
    assert "below floor" in text
    assert "need >=" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_margins_clean_low_floor(capsys):
    rc = admin.main(["margins", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "MARGIN GUARD" in out


def test_cli_margins_flags_high_floor(capsys):
    rc = admin.main(["margins", "70"])
    out = capsys.readouterr().out
    assert rc == 1  # non-zero when items are below floor
    assert "below floor" in out
