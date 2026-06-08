"""Dynamic pricing (uplift-only, margin-safe) + memory-based gift profiles."""
from datetime import datetime
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


# ── dynamic pricing ──

def test_multiplier_never_below_one():
    from quoteforge.etsy.dynamic_pricing import demand_multiplier
    for month in range(1, 13):
        m = demand_multiplier(datetime(2026, month, 15))
        assert m >= 1.0


def test_dynamic_price_never_below_list_or_floor():
    from quoteforge.etsy.dynamic_pricing import dynamic_price
    # Christmas window (mid-Nov) should add uplift
    peak = dynamic_price(49.99, cost=12.0, tier="entry", now=datetime(2026, 11, 15))
    assert peak["price"] >= peak["list_price"] >= 0
    assert peak["holds_floor"] and peak["margin_pct"] >= 60
    assert peak["multiplier"] >= 1.0


def test_dynamic_disabled_returns_list(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "DYNAMIC_PRICING_ENABLED", False)
    from quoteforge.etsy.dynamic_pricing import demand_multiplier
    assert demand_multiplier(datetime(2026, 11, 15)) == 1.0


# ── gift profiles ──

def test_save_and_get_profile(fresh_db):
    db = fresh_db
    pid = db.save_gift_profile("Owner@X.com", "Mom", "Mom", "Birthday",
                               event_date="03-15", notes="loves sage green")
    assert pid
    profs = db.get_gift_profiles("owner@x.com")
    assert len(profs) == 1 and profs[0]["recipient_name"] == "Mom"
    # upsert (same owner+recipient+occasion) doesn't duplicate
    db.save_gift_profile("owner@x.com", "Mom", "Mom", "Birthday", notes="new note")
    assert len(db.get_gift_profiles("owner@x.com")) == 1


def test_save_profile_requires_fields(fresh_db):
    assert fresh_db.save_gift_profile("", "Mom") == 0
    assert fresh_db.save_gift_profile("a@b.com", "") == 0


def test_upcoming_reminders(fresh_db):
    db = fresh_db
    now = datetime(2026, 3, 1)
    db.save_gift_profile("a@b.com", "Mom", "Mom", "Birthday", event_date="03-15")
    db.save_gift_profile("a@b.com", "Dad", "Dad", "Birthday", event_date="09-01")
    from quoteforge.marketing.gift_profiles import upcoming_gift_reminders
    rem = upcoming_gift_reminders(days_ahead=21, now=now)
    assert len(rem) == 1 and rem[0]["recipient_name"] == "Mom"


def test_profile_endpoint(fresh_db, monkeypatch):
    import pytest
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    monkeypatch.setattr("quoteforge.db.database.save_gift_profile",
                        lambda **k: 1)
    c = app.test_client()
    ok = c.post("/profile", json={"owner_email": "a@b.com", "recipient_name": "Mom",
                                  "occasion": "Birthday", "event_date": "03-15"})
    assert ok.status_code == 200 and ok.get_json()["status"] == "ok"
    bad = c.post("/profile", json={"owner_email": "a@b.com"})
    assert bad.status_code == 400


def test_gift_and_dynamic_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "dynamic-pricing" in COMMANDS and "gift-profiles" in COMMANDS
