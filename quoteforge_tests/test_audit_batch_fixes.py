"""Regression tests for the 2026-07-20 E2E audit batch (order-safety findings).

Each test pins one audited defect: consent/vendor-id destruction on re-create
(C3), native/duplicate routing downgrades (H4), the native-mode fallback and
monitor blindness (H6), autopilot claims bypassing the claim queue (H5/M11),
missing consent timestamps (M9), and the honesty fixes (A11/A12). Isolated DB
per test."""
import pytest

import quoteforge.db.database as db


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    db.init_db()
    return tmp_path


def _mk_order(order_id="ORD-1", **extra):
    data = {"order_id": order_id, "customer_email": "c@example.com",
            "customer_name": "C", "recipient_name": "R", **extra}
    return db.create_order(data)


def test_create_order_never_replaces_existing_row(iso_db):
    # REGRESSION (audit C3): INSERT OR REPLACE wiped proof_approved/
    # proof_approved_at/vendor_order_id on a same-id re-run (admin fix-photo,
    # webhook redelivery race) - destroying the consent record and blinding the
    # router's double-submit guard. An existing row must be preserved AS-IS.
    _mk_order("ORD-1")
    db.update_order("ORD-1", proof_approved=1,
                    proof_approved_at="2026-07-20 10:00:00",
                    vendor_order_id="GLT-123", gelato_order_id="GLT-123")
    rid = _mk_order("ORD-1", customer_name="Attacker Rewrite")
    assert rid == "ORD-1"
    row = db.get_order("ORD-1")
    assert row["proof_approved"] == 1                  # consent survived
    assert row["proof_approved_at"] == "2026-07-20 10:00:00"
    assert row["vendor_order_id"] == "GLT-123"         # idempotency guard intact
    assert row["customer_name"] == "C"                 # no silent rewrite either


def test_create_order_source_has_no_replace():
    # Belt: the destructive SQL can never quietly return (also infra check 96).
    import inspect
    src = inspect.getsource(db)
    assert "INSERT OR REPLACE INTO orders" not in src


def test_monitor_recognizes_native_vendor():
    # REGRESSION (audit H6): a native-mode order has no QuoteForge-side vendor id
    # BY DESIGN; it must not be a false missing-vendor-id violation.
    from quoteforge.automation.order_monitor import _has_vendor
    assert _has_vendor({"vendor": "gelato-native"}) is True
    assert _has_vendor({"vendor_order_id": "X"}) is True
    assert _has_vendor({"vendor": "gelato"}) is False


def test_router_mode_fallback_matches_config():
    # REGRESSION (audit H6): `or "native"` meant a set-but-EMPTY env var silently
    # flipped the shop into native mode (no submission, no tracking).
    import inspect
    from quoteforge.fulfillment import router
    assert 'or "quoteforge") == "native"' in inspect.getsource(router)


def test_orchestrator_handles_native_and_duplicate_on_both_paths():
    # REGRESSION (audit H4): an order already in flight (native integration or a
    # recorded duplicate) was downgraded to approved_ready_to_print - an
    # instruction to hand-submit it AGAIN (double print, double charge).
    import inspect
    from quoteforge.automation import pipeline_orchestrator as po
    src = inspect.getsource(po)
    assert src.count("no manual re-submit") >= 2       # auto path + resume path


def test_autopilot_replacement_stages_into_claim_queue(iso_db):
    # REGRESSION (audit H5/M11): auto_replacement called a stub filer (files
    # NOTHING) and wrote "replacement_filed" into the LIFECYCLE status column -
    # invisible to the claim queue (keyed on claim_status) while the customer was
    # promised a replacement. It must stage claim_status=supplier_review and
    # leave the fulfillment status machine alone.
    _mk_order("ORD-2")
    db.update_order("ORD-2", status="delivered")
    from quoteforge.automation.autopilot import AutoDecision, _execute
    d = AutoDecision(category="damaged", title="t", action="auto_replacement",
                     decision="d", confidence=0.9, risk="low", money_out=0.0,
                     auto=True, reason="r", customer_message="msg")
    _execute(d, "ORD-2")
    row = db.get_order("ORD-2")
    assert row["claim_status"] == "supplier_review"    # visible to the queue
    assert row["status"] == "delivered"                # lifecycle untouched


def test_autopilot_decline_adjudicates_in_claim_status(iso_db):
    _mk_order("ORD-3")
    db.update_order("ORD-3", status="delivered")
    from quoteforge.automation.autopilot import AutoDecision, _execute
    d = AutoDecision(category="changed_mind", title="t", action="auto_decline",
                     decision="d", confidence=0.9, risk="low", money_out=0.0,
                     auto=True, reason="r", customer_message="msg")
    _execute(d, "ORD-3")
    row = db.get_order("ORD-3")
    assert row["claim_status"] == "denied_customer_fault"
    assert row["status"] == "delivered"


def test_escalate_approval_reports_no_action(iso_db):
    # REGRESSION (audit A12): approving an "escalate" decision reported
    # "executed" while _execute did nothing - the owner believed action was taken.
    from quoteforge.db.database import enqueue_approval
    from quoteforge.automation.autopilot import execute_approved
    aid = enqueue_approval(kind="issue", ref="", summary="s",
                           proposed_action="escalate", payload="{}",
                           confidence=0.5, risk="high", status="pending")
    out = execute_approved(aid)
    assert out["status"] == "approved_no_action"


def test_update_order_rejects_non_identifier_fields(iso_db):
    # REGRESSION (audit A11): the SET clause interpolates field NAMES; a future
    # caller passing user-controlled names must hard-stop, not inject.
    _mk_order("ORD-4")
    with pytest.raises(ValueError):
        db.update_order("ORD-4", **{"status=?, sale_price": "0"})


def test_proof_approval_paths_always_stamp_timestamp():
    # REGRESSION (audit M9): two orchestrator paths set proof_approved with no
    # proof_approved_at - the dispute-evidence timestamp policy cites.
    import inspect
    import re
    from quoteforge.automation import pipeline_orchestrator as po
    src = inspect.getsource(po)
    assert not re.search(r"proof_approved=1\)", src), \
        "bare proof_approved write without its timestamp"


def test_owner_release_not_logged_as_customer_consent():
    # REGRESSION (audit M10): the admin customer-approved command logged
    # "Customer approved the proof" for an OWNER release with no on-screen record.
    import inspect
    from quoteforge.automation import customer_proof as cp
    src = inspect.getsource(cp)
    assert "Owner released to print" in src
    assert "no on-screen record" in src
