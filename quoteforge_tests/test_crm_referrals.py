"""CRM Dashboard + Referral/Loyalty Leaderboard (real data only)."""
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


# ── referrals / leaderboard ──

def test_leaderboard_empty(fresh_db):
    from quoteforge.analytics.referrals import leaderboard, format_leaderboard_text
    assert leaderboard() == []
    assert "No reward activity yet" in format_leaderboard_text()


def test_referral_and_review_points(fresh_db):
    from quoteforge.analytics.referrals import (record_referral,
                                                record_review_credit, leaderboard)
    record_referral("ref@x.com", "friend@y.com")
    record_referral("ref@x.com", "friend@y.com")   # idempotent
    record_review_credit("ref@x.com", "rev1")
    lb = leaderboard(sync_repeats=False)
    top = next(r for r in lb if r["email"] == "ref@x.com")
    assert top["referral"] == 50 and top["review"] == 20 and top["points"] == 70


def test_repeat_purchase_points(fresh_db):
    db = fresh_db
    db.create_order({"order_id": "o1", "customer_email": "a@b.com",
                     "sale_price": 50, "created_at": "2026-01-01T00:00:00"})
    db.create_order({"order_id": "o2", "customer_email": "a@b.com",
                     "sale_price": 40, "created_at": "2026-02-01T00:00:00"})
    db.create_order({"order_id": "o3", "customer_email": "a@b.com",
                     "sale_price": 30, "created_at": "2026-03-01T00:00:00"})
    from quoteforge.analytics.referrals import sync_repeat_purchase_points, leaderboard
    created = sync_repeat_purchase_points()
    assert created == 2  # 2nd and 3rd orders earn repeat points
    assert sync_repeat_purchase_points() == 0  # idempotent
    lb = leaderboard(sync_repeats=False)
    assert lb[0]["repeat_purchase"] == 60


# ── CRM ──

def test_crm_overview_empty(fresh_db):
    from quoteforge.analytics.crm import customer_list, format_crm_overview
    assert customer_list() == []
    assert "No customers yet" in format_crm_overview()


def test_customer_360(fresh_db):
    db = fresh_db
    db.create_order({"order_id": "o1", "customer_email": "pat@x.com",
                     "customer_name": "Pat", "sale_price": 80})
    db.create_order({"order_id": "o2", "customer_email": "pat@x.com",
                     "customer_name": "Pat", "sale_price": 20})
    db.save_gift_profile("pat@x.com", "Mom", "Mom", "Birthday")
    from quoteforge.analytics.crm import customer_360, format_customer_text
    c = customer_360("pat@x.com")
    assert c["order_count"] == 2 and c["revenue"] == 100.0 and c["is_repeat"]
    assert len(c["gift_profiles"]) == 1
    assert "CRM 360" in format_customer_text("pat@x.com")


def test_crm_overview_ranks_by_revenue(fresh_db):
    db = fresh_db
    db.create_order({"order_id": "a", "customer_email": "low@x.com", "sale_price": 10})
    db.create_order({"order_id": "b", "customer_email": "high@x.com", "sale_price": 90})
    from quoteforge.analytics.crm import customer_list
    rows = customer_list()
    assert rows[0]["email"] == "high@x.com"


def test_crm_and_leaderboard_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "crm" in COMMANDS and "leaderboard" in COMMANDS
