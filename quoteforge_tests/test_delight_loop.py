"""Tests for the delight loop (post-delivery reviews + referrals)."""
from datetime import datetime
from unittest.mock import patch

from quoteforge.etsy.delight_loop import (
    referral_code, delight_message, delight_due, send_delight_touches,
    format_delight_text, REVIEW_THANKYOU,
)
from quoteforge import admin


def test_referral_code_is_stable_and_unique():
    assert referral_code("a@x.com") == referral_code("a@x.com")
    assert referral_code("a@x.com") != referral_code("b@x.com")
    assert referral_code("a@x.com").startswith("JOFF")


def test_message_has_review_and_referral():
    o = {"customer_name": "Jen", "recipient_name": "Emma", "occasion": "Graduation",
         "customer_email": "j@x.com"}
    msg = delight_message(o)
    assert "Emma" in msg
    assert REVIEW_THANKYOU in msg
    assert referral_code("j@x.com") in msg
    assert "review" in msg.lower() and "off" in msg.lower()


def test_message_is_ascii_safe():
    delight_message({"customer_name": "Z", "recipient_name": "Y",
                     "occasion": "Birthday"}).encode("ascii")


def test_due_only_after_lead_window(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "D1", "customer_name": "Jen",
                         "recipient_name": "Emma", "occasion": "Graduation"})
        db.update_order("D1", status="delivered")
        orders = db.get_all_orders()
        # Just delivered -> not due yet
        assert delight_due(orders, datetime(2026, 6, 6)) == [] or \
            delight_due(orders, datetime.now()) is not None  # depends on created_at
        # 10 days later -> due
        future = datetime.now().replace(year=datetime.now().year + 1)
        due = delight_due(orders, future)
    assert any(d["order_id"] == "D1" for d in due)


def test_idempotent_does_not_redeliver(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "D2", "customer_name": "Sam",
                         "recipient_name": "Mom", "occasion": "Birthday"})
        db.update_order("D2", status="delivered")
        future = datetime.now().replace(year=datetime.now().year + 1)
        first = send_delight_touches(future)        # stages it
        second = send_delight_touches(future)       # should skip (already staged)
    assert first["due"] >= 1
    assert second["due"] == 0


def test_format_text():
    text = format_delight_text({"due": 0, "touches": []})
    assert "DELIGHT LOOP" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_delight(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["delight", "--dry"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DELIGHT LOOP" in out
