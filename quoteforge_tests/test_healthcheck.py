"""Tests for the application health check + alerting."""
from unittest.mock import patch

from quoteforge.automation.healthcheck import (
    check_database, check_storage, check_recent_backup, check_error_orders,
    check_scheduled_jobs, run_healthcheck, format_health_text, send_health_alert,
    EXPECTED_TASKS,
)
from quoteforge import admin


def _all_ok_tasks():
    return {t: "Ready" for t in EXPECTED_TASKS}


# ── Individual checks ────────────────────────────────────────────

def test_check_database_ok(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        c = check_database()
    assert c.status == "OK"


def test_check_storage_ok(tmp_path):
    with patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        c = check_storage()
    assert c.status == "OK"


def test_check_error_orders_flags_problems(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "E-1", "recipient_name": "X", "occasion": "Y"})
        db.update_order(oid, status="error")
        c = check_error_orders()
    assert c.status == "WARN"
    assert "E-1" in c.detail


def test_check_error_orders_clean(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        c = check_error_orders()
    assert c.status == "OK"


def test_scheduled_jobs_all_present():
    c = check_scheduled_jobs(query_fn=_all_ok_tasks)
    assert c.status == "OK"


def test_scheduled_jobs_missing_fails():
    def partial():
        return {"QuoteForge Daily Report": "Ready"}  # others missing
    c = check_scheduled_jobs(query_fn=partial)
    assert c.status == "FAIL"
    assert "missing" in c.detail


def test_scheduled_jobs_disabled_fails():
    def disabled():
        d = {t: "Ready" for t in EXPECTED_TASKS}
        d["QuoteForge Daily Report"] = "Disabled"
        return d
    c = check_scheduled_jobs(query_fn=disabled)
    assert c.status == "FAIL"
    assert "disabled" in c.detail.lower()


def test_scheduled_jobs_no_scheduler_warns():
    c = check_scheduled_jobs(query_fn=lambda: {})
    assert c.status == "WARN"


# ── Etsy token expiry (proactive, #182-P1) ───────────────────────

def test_token_status_skipped_in_test_mode():
    # Pre-launch (TEST_MODE / no creds) must never false-alarm. token_expiry_status
    # reads TEST_MODE/ETSY_API_KEY from config at call time, so patch there.
    from quoteforge.automation import etsy_auth
    import quoteforge.config as cfg
    with patch.object(cfg, "TEST_MODE", True), patch.object(cfg, "ETSY_API_KEY", ""):
        s = etsy_auth.token_expiry_status()
    assert s["ok"] is True and "skipped" in s["detail"]


def test_token_status_warns_when_expiring_without_refresh(tmp_path, monkeypatch):
    # REGRESSION (#182-P1): an access token near expiry with NO refresh token is the
    # one state that silently stalls order intake -> must surface as not-ok (WARN).
    import time
    from quoteforge.automation import etsy_auth
    import quoteforge.config as cfg
    tok = tmp_path / "etsy_tokens.json"
    tok.write_text('{"access_token": "a", "refresh_token": "", '
                   f'"expires_at": {time.time() + 60}}}')     # ~1 min left, no refresh
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(tok))
    with patch.object(cfg, "TEST_MODE", False), patch.object(cfg, "ETSY_API_KEY", "k"), \
         patch.object(cfg, "ETSY_REFRESH_TOKEN", ""):
        s = etsy_auth.token_expiry_status()
    assert s["ok"] is False and "refresh" in s["detail"].lower()


def test_token_status_ok_when_refreshable(tmp_path, monkeypatch):
    # Near expiry BUT a refresh token exists -> with_refresh recovers -> OK.
    import time
    from quoteforge.automation import etsy_auth
    import quoteforge.config as cfg
    tok = tmp_path / "etsy_tokens.json"
    tok.write_text('{"access_token": "a", "refresh_token": "r", '
                   f'"expires_at": {time.time() + 60}}}')
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(tok))
    with patch.object(cfg, "TEST_MODE", False), patch.object(cfg, "ETSY_API_KEY", "k"):
        s = etsy_auth.token_expiry_status()
    assert s["ok"] is True


# ── Aggregate ────────────────────────────────────────────────────

def test_run_healthcheck_overall_ok(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        db.backup_database(tmp_path / "db_backups")  # recent backup → OK
        result = run_healthcheck(query_fn=_all_ok_tasks)
    assert result["overall"] == "OK"
    assert len(result["checks"]) == 8   # + Sync Uptime (#182) + Etsy Token (#182-P1)


def test_run_healthcheck_overall_fail(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        result = run_healthcheck(query_fn=lambda: {"QuoteForge Daily Report": "Ready"})
    assert result["overall"] == "FAIL"


def test_format_health_text():
    result = {"overall": "OK", "timestamp": "2026-06-04T00:00:00",
              "checks": [{"name": "Database", "status": "OK", "detail": "5 orders"}]}
    text = format_health_text(result)
    assert "Health Check" in text
    assert "Database" in text


# ── Alerting ─────────────────────────────────────────────────────

def test_no_alert_when_healthy(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        db.backup_database(tmp_path / "db_backups")
        out = send_health_alert(query_fn=_all_ok_tasks)
    assert out["status"] == "ok_no_alert"


def test_alert_sent_on_failure(tmp_path):
    import quoteforge.db.database as db
    sent = {}

    def fake_email(subject, body):
        sent["subject"] = subject
        return {"status": "sent", "to": "x@y.com", "subject": subject}

    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.emailer._send_email", side_effect=fake_email):
        db.init_db()
        out = send_health_alert(query_fn=lambda: {})  # no tasks → WARN → alert
    assert out["status"] == "alert_sent"
    assert "Health" in sent["subject"]


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_healthcheck_runs(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck._query_windows_tasks",
               return_value=_all_ok_tasks()):
        db.init_db()
        db.backup_database(tmp_path / "db_backups")
        rc = admin.main(["healthcheck"])
    out = capsys.readouterr().out
    assert "Health Check" in out
    assert rc == 0
