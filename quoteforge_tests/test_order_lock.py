"""Order-lock regression tests.

Once the customer approves the proof (proof_approved set), the customer-approved
design fields lock: an edit that would CHANGE one raises OrderLockedError. This
protects against shipping a defective/mis-personalized item after submission.
Status, tracking, claim and shipping fields stay writable so the lifecycle keeps
advancing; an audited admin override (allow_locked=True) can still edit."""
from unittest.mock import patch

import pytest


def _db(tmp_path):
    import quoteforge.db.database as db
    db.DB_PATH, db.OUTPUT_DIR = tmp_path / "t.db", tmp_path
    db.init_db()
    return db


def test_locked_field_edit_rejected_after_approval(tmp_path):
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", tmp_path / "t.db"), \
         patch.object(database, "OUTPUT_DIR", tmp_path):
        db = _db(tmp_path)
        db.create_order({"order_id": "L1", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        db.update_order("L1", proof_approved=1)
        with pytest.raises(database.OrderLockedError):
            db.update_order("L1", recipient_name="Different Name")
        # The stored value is unchanged.
        assert db.get_order("L1")["recipient_name"] == "Emma"


def test_locked_field_same_value_is_noop_allowed(tmp_path):
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", tmp_path / "t.db"), \
         patch.object(database, "OUTPUT_DIR", tmp_path):
        db = _db(tmp_path)
        db.create_order({"order_id": "L2", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        db.update_order("L2", proof_approved=1)
        # Re-writing the SAME value must not raise.
        db.update_order("L2", recipient_name="Emma", occasion="Graduation")
        assert db.get_order("L2")["recipient_name"] == "Emma"


def test_admin_override_allows_locked_edit(tmp_path):
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", tmp_path / "t.db"), \
         patch.object(database, "OUTPUT_DIR", tmp_path):
        db = _db(tmp_path)
        db.create_order({"order_id": "L3", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        db.update_order("L3", proof_approved=1)
        db.update_order("L3", recipient_name="Corrected", allow_locked=True)
        assert db.get_order("L3")["recipient_name"] == "Corrected"


def test_unapproved_order_is_freely_editable(tmp_path):
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", tmp_path / "t.db"), \
         patch.object(database, "OUTPUT_DIR", tmp_path):
        db = _db(tmp_path)
        db.create_order({"order_id": "L4", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        # No approval yet -> edits allowed (the proof is still being iterated).
        db.update_order("L4", recipient_name="Emma Rose", size="24x36")
        assert db.get_order("L4")["recipient_name"] == "Emma Rose"


def test_lifecycle_fields_stay_writable_after_approval(tmp_path):
    import quoteforge.db.database as database
    with patch.object(database, "DB_PATH", tmp_path / "t.db"), \
         patch.object(database, "OUTPUT_DIR", tmp_path):
        db = _db(tmp_path)
        db.create_order({"order_id": "L5", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        db.update_order("L5", proof_approved=1)
        # Status / tracking / vendor / address must keep advancing post-approval.
        db.update_order("L5", status="shipped", vendor_order_id="GEL1",
                        carrier="USPS", ship_to="1 Main St")
        row = db.get_order("L5")
        assert row["status"] == "shipped" and row["vendor_order_id"] == "GEL1"
