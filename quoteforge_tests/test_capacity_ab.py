"""Production Capacity Monitor + Automated A/B testing (real data only)."""
from datetime import datetime
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


# ── capacity monitor ──

def test_capacity_empty(fresh_db):
    from quoteforge.automation.capacity_monitor import vendor_metrics, format_capacity_text
    assert vendor_metrics() == {}
    assert "No orders yet" in format_capacity_text()


def _mk(db, oid, vendor, created, **fields):
    db.create_order({"order_id": oid, "vendor": vendor, "sale_price": 50})
    db.update_order(oid, created_at=created, **fields)


def test_vendor_metrics_speed_and_defects(fresh_db):
    db = fresh_db
    _mk(db, "o1", "gelato", "2026-01-01T00:00:00", shipped_at="2026-01-03T00:00:00",
        delivered_at="2026-01-08T00:00:00", status="delivered")
    _mk(db, "o2", "gelato", "2026-01-01T00:00:00", status="refunded")
    from quoteforge.automation.capacity_monitor import vendor_metrics
    m = vendor_metrics()["gelato"]
    assert m["orders"] == 2 and m["avg_production_days"] == 2.0
    assert m["avg_shipping_days"] == 5.0 and m["defect_rate_pct"] == 50.0


def test_overdue_orders(fresh_db):
    db = fresh_db
    _mk(db, "late1", "gelato", "2026-01-01T00:00:00", status="received")
    from quoteforge.automation.capacity_monitor import overdue_orders
    late = overdue_orders(now=datetime(2026, 1, 20))
    assert late and late[0]["order_id"] == "late1" and late[0]["stage"] == "production"


def test_best_vendor(fresh_db):
    db = fresh_db
    _mk(db, "f", "fast", "2026-01-01T00:00:00", shipped_at="2026-01-02T00:00:00")
    _mk(db, "s", "slow", "2026-01-01T00:00:00", shipped_at="2026-01-06T00:00:00")
    from quoteforge.automation.capacity_monitor import best_vendor
    assert best_vendor() == "fast"


# ── A/B testing ──

def test_ab_config_and_empty(fresh_db):
    from quoteforge.analytics.ab_testing import experiments_config, experiment_stats
    cfg = experiments_config()
    assert "hero_headline" in cfg and cfg["hero_headline"]["variants"]
    s = experiment_stats("hero_headline")
    assert s["winner"] is None and not s["ready"]


def test_ab_records_and_rate(fresh_db):
    db = fresh_db
    for _ in range(10):
        db.record_ab_event("hero_headline", "A", "impression")
    for _ in range(3):
        db.record_ab_event("hero_headline", "A", "conversion")
    db.record_ab_event("hero_headline", "B", "impression")
    from quoteforge.analytics.ab_testing import experiment_stats
    s = experiment_stats("hero_headline")
    a = next(v for v in s["variants"] if v["variant"] == "A")
    assert a["impressions"] == 10 and a["conversions"] == 3 and a["cvr_pct"] == 30.0
    assert s["winner"] is None  # not enough sample


def test_ab_event_validation(fresh_db):
    assert fresh_db.record_ab_event("", "A", "impression") == 0
    assert fresh_db.record_ab_event("e", "A", "bogus") == 0


def test_capacity_ab_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "capacity" in COMMANDS and "ab" in COMMANDS
