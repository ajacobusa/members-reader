"""Tests for the automated go-live preflight checker."""
from quoteforge.preflight import (
    run_preflight, check_software, check_config, MANUAL_CHECKS, CheckResult,
)


def test_software_checks_all_pass():
    results = check_software()
    fails = [r for r in results if r.status == "FAIL"]
    assert fails == [], f"Software checks failed: {[(r.name, r.detail) for r in fails]}"


def test_software_covers_ha_recovery():
    names = {r.name for r in check_software()}
    # The HA/recovery work must be represented in preflight
    assert any("WAL" in n for n in names)
    assert any("Idempotency" in n for n in names)
    assert any("backup" in n.lower() for n in names)
    assert any("retry" in n.lower() or "transient" in n.lower() for n in names)
    assert any("signature" in n.lower() for n in names)
    assert any("pipeline" in n.lower() for n in names)


def test_config_reports_test_mode():
    results = check_config()
    names = {r.name for r in results}
    assert "TEST_MODE" in names
    assert "ANTHROPIC_API_KEY" in names
    assert "ETSY_WEBHOOK_SECRET" in names


def test_run_preflight_structure():
    report = run_preflight()
    assert "software" in report
    assert "config" in report
    assert "manual" in report
    assert isinstance(report["software_passed"], bool)


def test_software_passed_true_when_no_fails():
    report = run_preflight()
    # Core software has no FAILs in TEST_MODE; only CONFIG (waitress/keys)
    assert report["software_passed"] is True


def test_manual_checks_present():
    assert len(MANUAL_CHECKS) >= 8
    assert any("Physical print" in m for m in MANUAL_CHECKS)


def test_pipeline_check_runs_seven_stages():
    results = check_software()
    pipeline = next(r for r in results if "pipeline" in r.name.lower())
    assert pipeline.status == "PASS"
    assert "7 stages" in pipeline.detail
