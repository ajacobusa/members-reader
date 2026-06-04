"""Regression tests for the end-to-end audit fixes:
1. Daily report is scoped to TODAY (not all-time).
2. Customer approval moves the order off 'awaiting_customer_approval'.
"""
from datetime import datetime, timedelta
from unittest.mock import patch


# ── Finding 1: daily report reflects today, not all-time ─────────

def test_daily_report_counts_only_today(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.emailer import build_report_html
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        # One order today, one backdated 10 days
        db.create_order({"order_id": "TODAY-1", "recipient_name": "A",
                         "occasion": "X", "sale_price": 30.0, "gelato_cost": 11.0})
        db.update_order("TODAY-1", status="shipped")
        old = db.create_order({"order_id": "OLD-1", "recipient_name": "B",
                               "occasion": "Y", "sale_price": 50.0, "gelato_cost": 11.0})
        db.update_order(old, status="shipped",
                        created_at=(datetime.now() - timedelta(days=10)).isoformat())
        subject, body = build_report_html()
    # Subject reflects 1 order today, NOT 2 all-time
    assert "1 new orders today" in subject
    # Today's revenue is $30 (the old $50 order is excluded from "today")
    assert "$30.00" in body
    # All-time line still shows both orders' combined profit
    assert "All-time net profit" in body


# ── Finding 2: customer approval unsticks the order ──────────────

def test_customer_approval_changes_status(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.customer_proof import (
        prepare_customer_proof, record_customer_approval,
    )
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "AUD-1", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        prepare_customer_proof("AUD-1")
        assert db.get_order("AUD-1")["status"] == "awaiting_customer_approval"
        # Customer approves (manual-Gelato flow: no product uid / address)
        record_customer_approval("AUD-1")
        order = db.get_order("AUD-1")
    # BUG FIX: must no longer be stuck awaiting approval
    assert order["status"] == "approved_ready_to_print"
    assert order["proof_approved"] == 1


def test_approved_ready_counts_as_billable(tmp_path):
    """The new status must still count as revenue in financials/reports."""
    import quoteforge.db.database as db
    from quoteforge.etsy.financials import summarize
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "AUD-2", "recipient_name": "X",
                               "occasion": "Y", "sale_price": 30.0, "gelato_cost": 11.0})
        db.update_order(oid, status="approved_ready_to_print")
        s = summarize([db.get_order(oid)])
    assert s["order_count"] == 1
    assert s["revenue"] == 30.0


def test_cli_customer_approved_message_accurate(tmp_path, capsys):
    """The CLI message must match what actually happened (no false 'printing')."""
    import quoteforge.db.database as db
    from quoteforge import admin
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "AUD-3", "recipient_name": "Lee", "occasion": "Z"})
        admin.main(["customer-approved", "AUD-3"])
    out = capsys.readouterr().out
    # Honest message: ready to upload to Gelato, NOT "sent to printing"
    assert "approved_ready_to_print" in out or "upload the artwork to Gelato" in out
