"""Tests for secret generation, restore, daily report, and the admin CLI."""
from pathlib import Path
from unittest.mock import patch

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
