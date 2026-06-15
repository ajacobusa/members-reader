"""Tests for secret generation, restore, daily report, and the admin CLI."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from quoteforge.secrets_util import generate_webhook_secret
from quoteforge import admin


# ── Secret generation ────────────────────────────────────────────

def test_secret_is_long_and_unique():
    s1 = generate_webhook_secret()
    s2 = generate_webhook_secret()
    assert len(s1) >= 32
    assert s1 != s2  # cryptographically random


def test_secret_is_url_safe():
    s = generate_webhook_secret()
    assert all(c.isalnum() or c in "-_" for c in s)


# ── Restore (recovery drill) ─────────────────────────────────────

def test_restore_from_backup(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "R-1", "recipient_name": "Emma", "occasion": "Grad"})
        backup = db.backup_database(tmp_path / "bk")
        # simulate data loss: delete the order
        with db._conn() as c:
            c.execute("DELETE FROM orders")
        assert db.get_order("R-1") is None
        # restore
        restored = db.restore_database(backup)
        assert restored == backup
        assert db.get_order("R-1") is not None


def test_restore_none_when_no_backup(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        assert db.restore_database(backup_dir=tmp_path / "empty") is None


def test_list_backups(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.backup_database(tmp_path / "bk")
        backups = db.list_backups(tmp_path / "bk")
    assert len(backups) == 1


# ── Daily report ─────────────────────────────────────────────────

def test_daily_report_structure(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "D-1", "recipient_name": "A", "occasion": "B"})
        db.update_order(oid, status="error")
        db.save_review("D-1", "please review", scheduled_for="2026-07-01")
        report = db.daily_order_report()
    assert report["by_status"].get("error") == 1
    assert report["pending_reviews"] == 1
    assert any(o["order_id"] == "D-1" for o in report["needs_attention"])


# ── Admin CLI dispatch ───────────────────────────────────────────

def test_cli_gen_secret(capsys):
    rc = admin.main(["gen-secret"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ETSY_WEBHOOK_SECRET=" in out


def test_cli_unknown_command_returns_2():
    assert admin.main(["nonsense"]) == 2


def test_cli_no_args_prints_help():
    assert admin.main([]) == 0


def test_cli_daily_report(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        rc = admin.main(["daily-report"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DAILY ORDER REPORT" in out


def test_force_real_bypasses_test_mode_mock():
    """force_real=True must call the real client even when TEST_MODE is on."""
    from unittest.mock import MagicMock
    from quoteforge.quotes import generator
    raw = "Dear Emma,\nYou did it.\nProud of you.\nLove, Mom"
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=raw)]
    mock_client.messages.create.return_value = mock_msg
    with patch.object(generator, "TEST_MODE", True), \
         patch.object(generator, "ANTHROPIC_API_KEY", "test-key"), \
         patch.object(generator.anthropic, "Anthropic", return_value=mock_client):
        out = generator.generate_personal_message(
            relationship="To My Daughter", recipient_name="Emma",
            sender_name="Mom", occasion="Graduation", memory_or_story="",
            scenery="Mountains", output_style="Personal Letter",
            count=1, force_real=True,
        )
    # Real path returns the (mocked) Claude text, NOT the "[TEST MODE...]" mock
    assert out
    assert "TEST MODE" not in out[0]
    mock_client.messages.create.assert_called_once()


def test_verify_gelato_auth_no_key():
    from quoteforge.automation import gelato_api
    with patch.object(gelato_api, "GELATO_API_KEY", ""):
        result = gelato_api.verify_gelato_auth()
    assert result["ok"] is False
    assert "not set" in result["detail"]


def test_verify_gelato_auth_success():
    from quoteforge.automation import gelato_api
    fake = MagicMock()
    fake.status_code = 200
    with patch.object(gelato_api, "GELATO_API_KEY", "real-key"), \
         patch.object(gelato_api.requests, "get", return_value=fake):
        result = gelato_api.verify_gelato_auth()
    assert result["ok"] is True


def test_verify_gelato_auth_rejected():
    from quoteforge.automation import gelato_api
    fake = MagicMock()
    fake.status_code = 401
    with patch.object(gelato_api, "GELATO_API_KEY", "bad-key"), \
         patch.object(gelato_api.requests, "get", return_value=fake):
        result = gelato_api.verify_gelato_auth()
    assert result["ok"] is False
    assert "401" in result["detail"]


def test_cli_sample_quote_no_key(capsys):
    from quoteforge import config
    with patch.object(config, "ANTHROPIC_API_KEY", ""):
        rc = admin.main(["sample-quote"])
    assert rc == 1
    assert "ANTHROPIC_API_KEY not set" in capsys.readouterr().out


def test_cli_verify_keys_runs(capsys):
    from quoteforge import config
    with patch.object(config, "ANTHROPIC_API_KEY", ""):
        rc = admin.main(["verify-keys"])
    out = capsys.readouterr().out
    assert "Anthropic" in out and "Gelato" in out
    assert rc == 1  # nothing configured → not all verified


def test_cli_backup_and_list(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "BK-1", "recipient_name": "X", "occasion": "Y"})
        rc_backup = admin.main(["backup"])
        rc_list = admin.main(["list-backups"])
    assert rc_backup == 0
    assert rc_list == 0
    out = capsys.readouterr().out
    assert "Backup created" in out


# ── Owner-alert delivery is observable (the alerter can't fail silently) ──

def test_dispute_alert_skipped_send_is_logged(tmp_path, caplog):
    """If the mailer skips (creds unset) the alert must be logged, not discarded."""
    import logging
    import quoteforge.db.database as db
    from quoteforge.automation import dispute_scanner, emailer
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(dispute_scanner, "scan_etsy_disputes",
                      return_value={"status": "ok", "disputed": ["D-9"]}), \
         patch.object(emailer, "_send_email",
                      return_value={"status": "skipped", "message": "creds unset"}), \
         caplog.at_level(logging.WARNING, logger="quoteforge.admin"):
        rc = admin.main(["scan-disputes"])
    assert rc == 0
    assert any("D-9" in r.message or "skipped" in r.message.lower()
               or "not delivered" in r.message.lower()
               for r in caplog.records), "skipped send should be logged"
    assert caplog.records, "a warning should be emitted for a non-sent alert"


def test_dispute_alert_send_exception_is_logged(tmp_path, caplog):
    """If the mailer raises (bad/expired SMTP creds) the failure must be logged."""
    import logging
    import quoteforge.db.database as db
    from quoteforge.automation import dispute_scanner, emailer
    with patch.object(db, "DB_PATH", tmp_path / "live.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(dispute_scanner, "scan_etsy_disputes",
                      return_value={"status": "ok", "disputed": ["D-9"]}), \
         patch.object(emailer, "_send_email",
                      side_effect=RuntimeError("SMTP auth failed")), \
         caplog.at_level(logging.WARNING, logger="quoteforge.admin"):
        rc = admin.main(["scan-disputes"])
    # Alert stays non-blocking (no raise), but the failure is now visible.
    assert rc == 0
    assert any("SMTP auth failed" in r.message or "failed" in r.message.lower()
               for r in caplog.records), "raised send should be logged, not swallowed"
