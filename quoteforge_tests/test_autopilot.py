"""Tests for the autopilot decision bots + human-approval gate."""
from unittest.mock import patch

import pytest

from quoteforge.automation import autopilot
from quoteforge.automation.autopilot import (
    classify_issue, decide, handle_issue, execute_approved, autopilot_status,
)


@pytest.fixture
def db(tmp_path):
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", tmp_path / "t.db"), \
         patch.object(database, "OUTPUT_DIR", tmp_path):
        database.init_db()
        yield database


# ── Classifier ───────────────────────────────────────────────────

def test_classify_exact_and_alias():
    assert classify_issue("damaged_package")[1] >= 0.95
    cat, conf = classify_issue("the frame arrived broken")
    assert cat == "damaged_package" and conf >= 0.8


def test_classify_unknown_is_zero():
    assert classify_issue("hello there")[1] == 0.0


# ── Decision policy: auto vs escalate ────────────────────────────

def test_damage_auto_resolves_no_money_out():
    d = decide("my print arrived damaged")
    assert d.auto is True
    assert d.action == "auto_replacement"
    assert d.money_out == 0.0  # Gelato-covered


def test_clear_customer_fault_auto_declines():
    d = decide("I changed my mind")
    assert d.auto is True
    assert d.action == "auto_decline"


def test_cancellation_refund_escalates_to_human():
    # Money would leave the business -> never auto (cap is $0).
    d = decide("please cancel my order", {"sale_price": 40.0})
    assert d.auto is False
    assert d.risk == "high"
    assert "spend" in d.reason or "high-risk" in d.reason


def test_high_value_order_escalates():
    d = decide("my print arrived damaged", {"sale_price": 300.0})
    assert d.auto is False
    assert "high-value" in d.reason


def test_low_confidence_escalates():
    d = decide("something is weird with my thing")
    assert d.auto is False


def test_autopilot_disabled_escalates_everything():
    with patch.object(autopilot, "AUTOPILOT_ENABLED", False):
        d = decide("my print arrived damaged")
    assert d.auto is False
    assert "disabled" in d.reason


# ── End-to-end handling ──────────────────────────────────────────

def test_handle_damage_auto_executes(db):
    db.create_order({"order_id": "A1", "recipient_name": "Emma",
                     "occasion": "Graduation"})
    res = handle_issue("the canvas arrived torn", "A1")
    assert res["outcome"] == "auto-executed"
    order = db.get_order("A1")
    assert order["status"] == "replacement_filed"
    # A customer reply was staged.
    assert any("resolution:" in m["message_type"]
               for m in db.get_customer_messages("A1"))
    # An 'auto' audit row exists; nothing pending for the human.
    assert db.get_pending_approvals() == []


def test_handle_cancellation_queues_for_human(db):
    db.create_order({"order_id": "A2", "recipient_name": "Sam",
                     "occasion": "Wedding", "sale_price": 45.0})
    res = handle_issue("cancel please", "A2")
    assert res["outcome"] == "queued_for_human"
    pending = db.get_pending_approvals()
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"


def test_owner_approves_queued_decision_executes(db):
    db.create_order({"order_id": "A3", "recipient_name": "Sam",
                     "occasion": "Wedding", "sale_price": 45.0})
    res = handle_issue("wrong address, I mistyped it", "A3")
    # wrong_address is customer-fault, no money out -> actually auto. Use a
    # genuinely escalated one instead:
    if res["outcome"] != "queued_for_human":
        res = handle_issue("please cancel my order", "A3")
    aid = res["approval_id"]
    out = execute_approved(aid)
    assert out["status"] == "executed"
    assert db.get_approval(aid)["status"] == "approved"


def test_status_counts(db):
    db.create_order({"order_id": "A4", "recipient_name": "X", "occasion": "Y"})
    handle_issue("damaged in shipping", "A4")          # auto
    handle_issue("cancel my order", "A4")               # pending
    st = autopilot_status()
    assert st["pending_human"] == 1
    assert st["auto_last_24h"] >= 1


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_autopilot(db, capsys):
    from quoteforge import admin
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", db.DB_PATH), \
         patch.object(database, "OUTPUT_DIR", db.OUTPUT_DIR):
        rc = admin.main(["autopilot", "my poster arrived damaged"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AUTOPILOT DECISION" in out
