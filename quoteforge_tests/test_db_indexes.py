"""Hot order/lookup paths must hit an index, not a full table scan, so the order
pipeline stays fast as the orders table grows. REGRESSION for the pipeline-runtime
work: customer-email ownership lookups, vendor-order reconciliation, status filters,
and resume-by-email all use a covering index.
"""
import sqlite3

import pytest


def _plan(conn, sql):
    return " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    c = sqlite3.connect(db.DB_PATH)
    yield c
    c.close()


@pytest.mark.parametrize("sql,index", [
    ("SELECT * FROM orders WHERE customer_email='x'", "idx_orders_email"),
    ("SELECT * FROM orders WHERE gelato_order_id='x'", "idx_orders_gelato"),
    ("SELECT * FROM orders WHERE status='received'", "idx_orders_status"),
    ("SELECT * FROM saved_designs WHERE email='x'", "idx_saved_designs_email"),
])
def test_hot_lookup_uses_index(conn, sql, index):
    plan = _plan(conn, sql)
    assert "USING INDEX" in plan and index in plan, f"{sql} -> {plan}"
    assert "SCAN orders" not in plan  # never a full scan on the hot path


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    # Re-running init_db (every process start / migration) must not raise and must
    # keep the indexes - CREATE INDEX IF NOT EXISTS is additive.
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.init_db()
    c = sqlite3.connect(db.DB_PATH)
    idx = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    c.close()
    assert {"idx_orders_email", "idx_orders_gelato",
            "idx_saved_designs_email"} <= idx
