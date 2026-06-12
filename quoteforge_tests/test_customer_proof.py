"""Tests for the customer proof-approval workflow."""
from pathlib import Path
from unittest.mock import patch

from quoteforge import admin


def test_prepare_customer_proof_blocks_printing(tmp_path):
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
    # Order is parked awaiting the customer; a proof message was saved
    assert order["status"] == "awaiting_customer_approval"
    assert "Emma" in pkg["proof_message"]
    # Final-approval model: the buyer is never asked to reply APPROVED -
    # they only reply if something needs CHANGING (fix-it window).
    assert "APPROVED" not in pkg["proof_message"]
    assert "reply within 24 hours" in pkg["proof_message"]
    assert pkg["artwork_path"] == "/path/art.png"
    assert any(m["message_type"] == "Proof Ready" for m in msgs)


def test_record_customer_approval_releases_order(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.customer_proof import (
        prepare_customer_proof, record_customer_approval,
    )
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "P-2", "recipient_name": "Sam", "occasion": "Wedding"})
        prepare_customer_proof("P-2")
        # No Gelato product/address → resume runs but stays unshipped; the point
        # is the proof_approved flag flips and it's no longer awaiting customer.
        record_customer_approval("P-2")
        order = db.get_order("P-2")
        log = db.get_pipeline_log("P-2")
    assert order["proof_approved"] == 1
    stages = [(l["stage"], l["status"]) for l in log]
    assert ("proof", "awaiting_customer") in stages
    assert ("proof", "customer_approved") in stages


def test_pipeline_pauses_for_customer_when_enabled(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "CUSTOMER_PROOF_APPROVAL", True), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", False), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None):
        db.init_db()
        result = po.run_full_pipeline(
            {"order_id": "P-3", "recipient_name": "Emma", "occasion": "Graduation",
             "sender_name": "Mom", "relationship": "To My Daughter"},
            skip_proof=False,  # do NOT skip — we want the customer-proof pause
        )
        msgs = db.get_customer_messages("P-3")
    # Pipeline stopped at customer approval; design was made but NOT shipped
    assert result["status"] == "awaiting_customer_approval"
    assert result["generated_quote"]
    assert any(m["message_type"] == "Proof Ready" for m in msgs)
    # Real poster still produced for the buyer to review
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
    assert "PROOF TO SEND TO BUYER" in out
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
