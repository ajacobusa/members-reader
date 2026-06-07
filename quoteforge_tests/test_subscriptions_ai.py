"""Tests for subscriptions DB, expiry reminders, and AI helpers (TEST_MODE)."""
from datetime import date, timedelta


def test_ai_text_returns_mock_in_test_mode(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.ai.assistant import ai_text, gift_note, subscription_renewal_email
    assert ai_text("prompt", "op", mock="FALLBACK") == "FALLBACK"
    note = gift_note("Mom", "Sam", "Birthday")
    assert "Mom" in note and "Sam" in note
    email = subscription_renewal_email("Sam", "monthly", 3, "Joffiels")
    assert "Sam" in email and "Joffiels" in email and "3 day" in email


def test_subscription_crud_and_expiring(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    soon = (date.today() + timedelta(days=3)).isoformat()
    far = (date.today() + timedelta(days=60)).isoformat()
    db.add_subscription("a@x.com", soon, "Ann", "monthly")
    db.add_subscription("b@x.com", far, "Bob", "annual")
    exp = db.get_expiring_subscriptions(within_days=7)
    assert len(exp) == 1 and exp[0]["customer_email"] == "a@x.com"


def test_expiry_reminders_send_and_are_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    sent = []
    monkeypatch.setattr("quoteforge.automation.emailer._send_email",
                        lambda s, b, to="": sent.append(to))
    from quoteforge.db import database as db
    from quoteforge.etsy.subscriptions import send_expiry_reminders
    db.init_db()
    db.add_subscription("a@x.com", (date.today() + timedelta(days=2)).isoformat(), "Ann")
    r1 = send_expiry_reminders(within_days=7)
    assert r1["due"] == 1 and sent == ["a@x.com"]
    r2 = send_expiry_reminders(within_days=7)        # already reminded -> no resend
    assert r2["due"] == 0


def test_gift_addon_listing_shape():
    from quoteforge.etsy.gift_ecard import build_addon_listing
    l = build_addon_listing()
    assert len(l["title"]) <= 140 and len(l["tags"]) == 13
    assert "EMAIL" in l["personalization"] and l["price"] > 0
    assert "marketing list unless they choose" in l["description"]
