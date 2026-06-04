"""Tests for the daily self-healing maintenance agent."""
from unittest.mock import patch

from quoteforge.automation import maintenance
from quoteforge.automation.maintenance import (
    run_maintenance, measure_performance, suggest_enhancements,
    format_maintenance_text,
)
from quoteforge import admin


def _all_jobs_present():
    """A query_fn that reports every expected scheduled job as Ready."""
    from quoteforge.automation.scheduler import EXPECTED_TASK_NAMES
    return {name: "Ready" for name in EXPECTED_TASK_NAMES}


def _jobs_missing():
    # Task Scheduler is readable, but our QuoteForge jobs aren't registered ->
    # the Scheduled Jobs check reports them as "missing" (a FAIL we can heal).
    return {"Some Unrelated Windows Task": "Ready"}


def test_measure_performance(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        perf = measure_performance()
    assert perf["orders_total"] == 0
    assert perf["stats_query_ms"] >= 0
    assert "by_status" in perf


def test_db_maintenance_vacuums(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        m = db.db_maintenance()
    assert m["ran"] is True
    assert m["integrity"] == "ok"
    assert "reclaimed_kb" in m


def test_check_only_mode_changes_nothing(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        report = run_maintenance(fix=False, query_fn=_jobs_missing)
    assert report["mode"] == "check-only"
    # Every action must be skipped — nothing healed in check mode
    assert all("skipped" in a["status"] for a in report["actions"])


def test_heal_reinstalls_missing_jobs(tmp_path):
    import quoteforge.db.database as db
    called = {}

    def fake_install(**kwargs):
        called["installed"] = True
        return {"total": 9, "errors": 0, "results": []}

    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.scheduler.install_schedule", fake_install):
        db.init_db()
        report = run_maintenance(fix=True, query_fn=_jobs_missing)
    assert called.get("installed") is True
    job_fix = [a for a in report["actions"] if a["action"] == "reinstall scheduled jobs"][0]
    assert job_fix["status"] == "fixed"


def test_healthy_infra_reports_ok(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        db.backup_database()  # so the backup check passes
        report = run_maintenance(fix=True, query_fn=_all_jobs_present)
    assert report["overall"] in ("OK", "ACTION")  # db vacuum counts as an action
    assert report["health"]["overall"] == "OK"


def test_integrity_failure_raises_alert(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path), \
         patch.object(db, "db_maintenance",
                      return_value={"ran": True, "integrity": "corruption detected"}):
        db.init_db()
        report = run_maintenance(fix=True, query_fn=_all_jobs_present)
    assert report["overall"] == "ALERT"
    db_action = [a for a in report["actions"] if a["action"] == "db maintenance"][0]
    assert db_action["status"] == "ALERT"


def test_suggestions_flag_errored_orders():
    perf = {"orders_total": 5, "stats_query_ms": 10, "db_size_kb": 100,
            "by_status": {"error": 2}}
    tips = suggest_enhancements(perf, {"overall": "WARN"})
    assert any("error" in t.lower() for t in tips)


def test_suggestions_clean_when_healthy():
    perf = {"orders_total": 3, "stats_query_ms": 5, "db_size_kb": 50,
            "by_status": {"shipped": 3}}
    # Isolate the "all clear" path — margins are covered by their own tests.
    with patch("quoteforge.etsy.margin_guard.audit_catalog",
               return_value={"below_floor": 0, "offenders": [], "floor_pct": 50}):
        tips = suggest_enhancements(perf, {"overall": "OK"})
    assert any("no issues" in t.lower() or "no action" in t.lower() for t in tips)


def test_suggestions_flag_margin_erosion():
    perf = {"orders_total": 3, "stats_query_ms": 5, "db_size_kb": 50,
            "by_status": {"shipped": 3}}
    fake = {"below_floor": 2, "floor_pct": 50,
            "offenders": [{"name": "Hoodie", "margin_pct": 39}]}
    with patch("quoteforge.etsy.margin_guard.audit_catalog", return_value=fake):
        tips = suggest_enhancements(perf, {"overall": "OK"})
    assert any("margin floor" in t.lower() for t in tips)


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_maintenance_registered():
    assert "maintenance" in admin.COMMANDS


def test_cli_maintenance_check(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        admin.main(["maintenance", "--check"])
    out = capsys.readouterr().out
    assert "Daily Maintenance" in out
    assert "ENHANCEMENT SUGGESTIONS" in out
    assert "PERFORMANCE" in out
