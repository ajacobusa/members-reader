"""Tests for high-availability, recovery, and resilience fixes:
WAL/concurrency, idempotency, DB backup, atomic webhook log, retry/backoff."""
import json
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── SQLite hardening (WAL + busy_timeout) ────────────────────────

def test_wal_mode_enabled(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db, _conn
        init_db()
        with _conn() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


def test_concurrent_writes_do_not_lock(tmp_path):
    """Many threads writing at once should not raise 'database is locked'."""
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db, create_order
        init_db()
        errors = []

        def write(i):
            try:
                create_order({"order_id": f"C-{i}", "recipient_name": "X", "occasion": "Y"})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"Concurrent writes failed: {errors}"


# ── Idempotency ──────────────────────────────────────────────────

def test_get_order_by_etsy_id(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db, create_order, get_order_by_etsy_id
        init_db()
        create_order({"order_id": "QF-1", "etsy_order_id": "ETSY-99",
                      "recipient_name": "Emma", "occasion": "Graduation"})
        found = get_order_by_etsy_id("ETSY-99")
        assert found is not None
        assert found["order_id"] == "QF-1"
        assert get_order_by_etsy_id("DOES-NOT-EXIST") is None


def test_webhook_idempotent_skips_duplicate(tmp_path):
    """A repeated webhook for the same Etsy order is skipped, not reprocessed."""
    payload = {
        "recipient_name": "Emma", "occasion": "Graduation",
        "order_id": "ETSY-DUP-1", "customer_name": "Jen",
    }
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.webhook_server.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        from quoteforge.automation.webhook_server import process_webhook_payload
        first = process_webhook_payload(payload)
        second = process_webhook_payload(payload)
    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert "already processed" in second["message"].lower()


def test_webhook_routes_to_db(tmp_path):
    """Webhook orders must land in the database (visible to the monitor)."""
    payload = {
        "recipient_name": "Emma", "occasion": "Graduation",
        "order_id": "ETSY-DB-1", "customer_name": "Jen",
    }
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.webhook_server.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        from quoteforge.automation.webhook_server import process_webhook_payload
        from quoteforge.db.database import get_order_by_etsy_id
        process_webhook_payload(payload)
        order = get_order_by_etsy_id("ETSY-DB-1")
    assert order is not None
    assert order["recipient_name"] == "Emma"


# ── DB backup / recovery ─────────────────────────────────────────

def test_backup_database_creates_snapshot(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db, create_order, backup_database
        init_db()
        create_order({"order_id": "B-1", "recipient_name": "X", "occasion": "Y"})
        backup_path = backup_database(tmp_path / "backups")
    assert backup_path is not None
    assert backup_path.exists()
    # backup is a valid SQLite DB containing the order
    conn = sqlite3.connect(backup_path)
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    assert count == 1


def test_backup_none_when_no_db(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "nope.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import backup_database
        assert backup_database(tmp_path / "backups") is None


def test_prune_old_backups(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import prune_old_backups
        bdir = tmp_path / "backups"
        bdir.mkdir()
        for i in range(20):
            (bdir / f"quoteforge_2026010{i:02d}_000000.db").write_text("x")
        deleted = prune_old_backups(bdir, keep=14)
    assert deleted == 6
    assert len(list(bdir.glob("quoteforge_*.db"))) == 14


def test_prune_age_based_keeps_only_3_days(tmp_path):
    import os, time
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.config.BACKUP_RETENTION_DAYS", 3):
        from quoteforge.db.database import prune_old_backups
        bdir = tmp_path / "backups"
        bdir.mkdir()
        now = time.time()
        # 2 recent (within 3 days) + 4 old (>3 days)
        ages_days = [0, 1, 5, 10, 20, 40]
        for i, d in enumerate(ages_days):
            f = bdir / f"quoteforge_2026{i:02d}01_000000.db"
            f.write_text("x")
            t = now - d * 86400
            os.utime(f, (t, t))
        deleted = prune_old_backups(bdir)  # age-based, 3-day retention
    remaining = list(bdir.glob("quoteforge_*.db"))
    assert deleted == 4              # the 5/10/20/40-day-old ones
    assert len(remaining) == 2       # only the 0 and 1-day-old


def test_prune_age_based_always_keeps_newest(tmp_path):
    import os, time
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.config.BACKUP_RETENTION_DAYS", 3):
        from quoteforge.db.database import prune_old_backups
        bdir = tmp_path / "backups"
        bdir.mkdir()
        now = time.time()
        # All backups are old — newest must still survive (never zero backups).
        for i, d in enumerate([10, 30, 90]):
            f = bdir / f"quoteforge_2026{i:02d}01_000000.db"
            f.write_text("x")
            t = now - d * 86400
            os.utime(f, (t, t))
        prune_old_backups(bdir)
    assert len(list(bdir.glob("quoteforge_*.db"))) == 1  # newest kept


# ── Atomic webhook log ───────────────────────────────────────────

def test_webhook_log_atomic_under_concurrency(tmp_path):
    with patch("quoteforge.automation.webhook_server.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.webhook_server.WEBHOOK_LOG", tmp_path / "wl.json"):
        from quoteforge.automation.webhook_server import _append_webhook_log

        def append(i):
            _append_webhook_log({"order_id": f"O-{i}", "status": "ok"})

        threads = [threading.Thread(target=append, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        entries = json.loads((tmp_path / "wl.json").read_text())
    # All 30 entries present — none lost to a race
    assert len(entries) == 30


# ── Retry / backoff ──────────────────────────────────────────────

def test_retry_succeeds_after_transient_failures():
    from quoteforge.automation.retry import retry_call

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            err = ConnectionError("temporary")
            raise err
        return "ok"

    with patch("quoteforge.automation.retry.time.sleep"):
        result = retry_call(flaky, max_attempts=3, base_delay=0.01)
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_does_not_retry_permanent_error():
    from quoteforge.automation.retry import retry_call

    calls = {"n": 0}

    def bad_request():
        calls["n"] += 1
        resp = MagicMock()
        resp.status_code = 400
        err = Exception("bad request")
        err.response = resp
        raise err

    with patch("quoteforge.automation.retry.time.sleep"):
        with pytest.raises(Exception):
            retry_call(bad_request, max_attempts=3, base_delay=0.01)
    assert calls["n"] == 1  # not retried


def test_is_transient_classification():
    from quoteforge.automation.retry import is_transient

    resp503 = MagicMock(); resp503.status_code = 503
    e503 = Exception(); e503.response = resp503
    assert is_transient(e503) is True

    resp400 = MagicMock(); resp400.status_code = 400
    e400 = Exception(); e400.response = resp400
    assert is_transient(e400) is False

    assert is_transient(TimeoutError("slow")) is True
