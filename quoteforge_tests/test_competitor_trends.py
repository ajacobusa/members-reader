"""Competitor Intelligence + Trend Prediction Engine (real data only)."""
from datetime import datetime
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


# ── competitor intelligence ──

def test_competitor_empty(fresh_db, monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "COMPETITORS", [])
    from quoteforge.analytics.competitor_intel import alerts, format_competitor_text
    assert alerts() == []
    assert "No competitors configured" in format_competitor_text()


def test_price_drop_and_new_listing_alerts(fresh_db, monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "COMPETITORS", ["RivalArt"])
    monkeypatch.setattr(cfg, "COMPETITOR_PRICE_DROP_ALERT_PCT", 10.0)
    from quoteforge.analytics.competitor_intel import record, alerts
    record("RivalArt", listings=100, min_price=40.0, reviews=500)
    record("RivalArt", listings=105, min_price=30.0, reviews=520)
    al = alerts("RivalArt")
    types = {a["type"] for a in al}
    assert "price_drop" in types and "new_listings" in types and "review_growth" in types


def test_small_price_change_no_alert(fresh_db, monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "COMPETITORS", ["RivalArt"])
    monkeypatch.setattr(cfg, "COMPETITOR_PRICE_DROP_ALERT_PCT", 10.0)
    from quoteforge.analytics.competitor_intel import record, alerts
    record("RivalArt", min_price=40.0)
    record("RivalArt", min_price=39.0)  # only 2.5% drop
    assert not any(a["type"] == "price_drop" for a in alerts("RivalArt"))


# ── trend prediction ──

def test_seasonal_signals_present():
    from quoteforge.analytics.trend_engine import seasonal_signals
    sigs = seasonal_signals(now=datetime(2026, 8, 20), horizon_days=120)
    assert isinstance(sigs, list) and sigs  # always some upcoming season

def test_rising_demand(fresh_db):
    db = fresh_db
    # earlier: mostly Birthday; later: surge in Wedding
    for i in range(4):
        db.create_order({"order_id": f"e{i}", "occasion": "Birthday",
                         "created_at": f"2026-01-0{i+1}T00:00:00"})
    for i in range(4):
        db.create_order({"order_id": f"l{i}", "occasion": "Wedding",
                         "created_at": f"2026-03-0{i+1}T00:00:00"})
    from quoteforge.analytics.trend_engine import rising_demand
    r = rising_demand()
    assert r and r[0]["occasion"] == "Wedding" and r[0]["delta"] > 0


def test_predict_outputs(fresh_db):
    from quoteforge.analytics.trend_engine import predict, format_trend_text
    d = predict(now=datetime(2026, 8, 20))
    assert "holiday_recommendations" in d and "new_listing_ideas" in d
    assert "Trend Prediction Engine" in format_trend_text(now=datetime(2026, 8, 20))


def test_competitor_trends_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "competitors" in COMMANDS and "trends" in COMMANDS
