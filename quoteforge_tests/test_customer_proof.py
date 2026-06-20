"""Tests for the proof model: on-screen approval is the final sign-off, with an
owner-review fail-safe for any order that has no approval on record.

REGRESSION: the emailed/messaged "we send a proof, reply within 24h to change
it" round is retired everywhere. The customer approves on screen at checkout
(recorded as proof_approved at order creation); any unapproved order HOLDS for
owner review and is never auto-printed or sent a customer proof email.
"""
from unittest.mock import patch

from quoteforge import admin


def test_onscreen_order_records_approval(tmp_path):
    # REGRESSION (Part 2a): a direct on-screen order records proof_approved + an
    # audit timestamp at creation - disputes evidence, the post-approval field
    # lock and the production-without-approval monitor all key off this.
    import quoteforge.db.database as db
    import quoteforge.automation.design_confirm as dc
    design = ('{"contact": {"name": "Dana", "addr": "1 Main St", '
              '"country": "US", "state": "CA"}}')
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        res = dc.confirm_design("dana@example.com", design_json=design,
                                design_id="d1", send=False)
        order = db.get_order(res["order_id"])
    assert res["order_id"]
    assert order["proof_approved"] == 1
    assert order["proof_approved_at"]          # immutable approval timestamp


def test_prepare_proof_holds_for_owner_review(tmp_path):
    # The manual fail-safe parks an unapproved order pending OWNER review and
    # blocks printing - with no buyer message and no "reply within 24h" round.
    import quoteforge.db.database as db
    from quoteforge.automation.customer_proof import prepare_customer_proof
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "P-1", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        pkg = prepare_customer_proof("P-1", artwork_path="/path/art.png")
        order = db.get_order("P-1")
        msgs = db.get_customer_messages("P-1")
    assert order["status"] == "awaiting_customer_approval"   # legacy held token
    assert order["proof_approved"] in (0, None)              # still not approved
    assert "Emma" in pkg["proof_message"]
    # No retired email-proof-round language, and no buyer message was staged.
    assert "reply within 24 hours" not in pkg["proof_message"].lower()
    assert "etsy" not in pkg["proof_message"].lower()
    assert not any(m["message_type"] == "Proof Ready" for m in msgs)
    assert pkg["artwork_path"] == "/path/art.png"


def test_record_approval_releases_order(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.customer_proof import (
        prepare_customer_proof, record_customer_approval,
    )
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "P-2", "recipient_name": "Sam", "occasion": "Wedding"})
        prepare_customer_proof("P-2")
        # No Gelato product/address -> resume runs but stays unshipped; the point
        # is proof_approved flips and it's released from the held state.
        record_customer_approval("P-2")
        order = db.get_order("P-2")
        log = db.get_pipeline_log("P-2")
    assert order["proof_approved"] == 1
    assert ("proof", "customer_approved") in [(l["stage"], l["status"]) for l in log]


def test_pipeline_holds_unapproved_order_for_owner(tmp_path):
    # REGRESSION (Part 2b): with no on-screen approval on record, the pipeline
    # HOLDS for owner review - it does NOT email a customer proof and does NOT
    # route to production. The artwork is still produced for the review.
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", False), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None):
        db.init_db()
        result = po.run_full_pipeline(
            {"order_id": "P-3", "recipient_name": "Emma", "occasion": "Graduation",
             "sender_name": "Mom", "relationship": "To My Daughter"},
            skip_proof=False,   # do NOT skip - we want the owner-review hold
        )
        msgs = db.get_customer_messages("P-3")
    # Held: not approved, not routed to production, but the design was made.
    assert not result.get("proof_approved")
    assert not result.get("vendor_order_id")
    assert result.get("status") not in ("in_production", "shipped")
    assert not any(m["message_type"] == "Proof Ready" for m in msgs)
    assert (tmp_path / "pipeline" / "P-3" / "artwork.png").exists()


def test_cli_show_proof(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "P-4", "recipient_name": "Ava", "occasion": "Birthday"})
        rc = admin.main(["show-proof", "P-4"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PROOF FOR OWNER REVIEW" in out
    assert "Ava" in out


def test_cli_customer_approved(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "P-5", "recipient_name": "Lee", "occasion": "Anniversary"})
        rc = admin.main(["customer-approved", "P-5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "approval recorded" in out.lower()


def test_cli_proof_unknown_order(capsys):
    rc = admin.main(["show-proof", "NOPE-999"])
    assert rc == 1
    assert "not found" in capsys.readouterr().out.lower()
