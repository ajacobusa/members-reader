"""Customer service request intake: validate a customer-submitted return/refund
request against the order record (order id, email-on-order, supplier order id,
tracking/delivery, claim window, evidence) and drive the review state machine.
Every request becomes documented + validated instead of handled casually."""
from datetime import datetime, timedelta


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    db.create_order({"order_id": "QF-1", "etsy_order_id": "E1",
                     "customer_email": "buyer@mail.com", "recipient_name": "Ann",
                     "occasion": "Birthday"})
    db.update_order("QF-1", status="delivered", delivery_confirmed=1,
                    gelato_order_id="GEL9", carrier="USPS",
                    delivered_at=(datetime.now() - timedelta(days=2)).isoformat())
    return db


def _req(**kw):
    base = {"order_number": "E1", "name": "Ann", "email": "buyer@mail.com",
            "issue_type": "Damaged item", "description": "corner crushed",
            "photos": ["product", "packaging"]}
    base.update(kw)
    return base


def test_issue_types_and_states_exposed():
    from quoteforge.fulfillment.claim_service import ISSUE_TYPES, CLAIM_STATES
    for t in ("Damaged item", "Printing defect", "Wrong item received",
              "Missing item", "Lost package", "Other"):
        assert t in ISSUE_TYPES
    for s in ("new", "validating_order", "evidence_review", "supplier_review",
              "approved_reprint", "approved_refund", "denied", "needs_more_info"):
        assert s in CLAIM_STATES


def test_valid_damage_claim_recommends_supplier_review(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req())
    c = r["checks"]
    assert c["order_found"] and c["email_matches"] and c["supplier_order_id"]
    assert c["within_window"] and c["evidence_complete"]
    assert r["supplier_order_ref"] == "GEL9"
    assert r["recommended_status"] == "supplier_review"


def test_email_mismatch_needs_more_info(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req(email="someone@else.com"))
    assert r["checks"]["email_matches"] is False
    assert r["recommended_status"] == "needs_more_info"


def test_unknown_order_needs_more_info(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req(order_number="NOPE"))
    assert r["checks"]["order_found"] is False
    assert r["recommended_status"] == "needs_more_info"


def test_missing_packaging_photo_needs_more_info(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req(photos=["product"]))   # damage needs packaging too
    assert r["checks"]["evidence_complete"] is False
    assert "packaging" in r["missing_evidence"]
    assert r["recommended_status"] == "needs_more_info"


def test_past_window_is_denied(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.update_order("QF-1", delivered_at=(datetime.now() - timedelta(days=40)).isoformat())
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req())
    assert r["checks"]["within_window"] is False
    assert r["recommended_status"] == "denied"


def test_day8_claim_held_for_admin_not_auto_approved(tmp_path, monkeypatch):
    # REGRESSION: past the 7-day customer window but still inside the supplier
    # window, a claim is NOT auto-approved (within_window False, not
    # supplier_review) and NOT auto-denied - it is held for an admin decision,
    # because the supplier still covers a free reprint.
    db = _seed(tmp_path, monkeypatch)
    db.update_order("QF-1", delivered_at=(datetime.now() - timedelta(days=8)).isoformat())
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req())
    assert r["checks"]["within_window"] is False
    assert r["checks"]["requires_admin_review"] is True
    assert r["recommended_status"] == "needs_more_info"
    assert r["recommended_status"] != "supplier_review"   # never auto-accepted


def test_past_supplier_window_is_denied(tmp_path, monkeypatch):
    # Past the supplier window (>30d) there is no coverage -> denied.
    db = _seed(tmp_path, monkeypatch)
    db.update_order("QF-1", delivered_at=(datetime.now() - timedelta(days=45)).isoformat())
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req())
    assert r["recommended_status"] == "denied"


def test_admin_override_allows_out_of_window_claim(tmp_path, monkeypatch):
    # REGRESSION: an admin override is the ONLY way to advance a past-window claim.
    db = _seed(tmp_path, monkeypatch)
    db.update_order("QF-1", delivered_at=(datetime.now() - timedelta(days=20)).isoformat())
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req(admin_override=True))
    assert r["checks"]["within_window"] is True
    assert r["checks"]["admin_override"] is True
    assert r["recommended_status"] == "supplier_review"


def test_day7_claim_still_in_window(tmp_path, monkeypatch):
    # Boundary: day 7 is the last eligible day (no override needed).
    db = _seed(tmp_path, monkeypatch)
    db.update_order("QF-1", delivered_at=(datetime.now() - timedelta(days=7)).isoformat())
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req())
    assert r["checks"]["within_window"] is True
    assert r["recommended_status"] == "supplier_review"


def test_lost_package_needs_no_photos(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request(_req(issue_type="Lost package", photos=[]))
    assert r["checks"]["evidence_complete"] is True
    assert r["recommended_status"] == "supplier_review"


def test_state_machine_transitions():
    from quoteforge.fulfillment.claim_service import advance_claim
    assert advance_claim("new", "validating_order")["ok"] is True
    assert advance_claim("supplier_review", "approved_reprint")["ok"] is True
    assert advance_claim("approved_reprint", "new")["ok"] is False   # terminal
    assert advance_claim("new", "approved_refund")["ok"] is False    # skips review


def test_customer_ack_is_individual_review_language():
    from quoteforge.fulfillment.claim_service import CUSTOMER_ACK
    assert "reviewed individually" in CUSTOMER_ACK
    assert "custom" in CUSTOMER_ACK.lower()


def test_intake_persists_request_and_status(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.claim_service import intake_claim
    r = intake_claim(_req())
    assert r["recommended_status"] == "supplier_review"
    row = db.get_order("QF-1")
    assert row["claim_status"] == "supplier_review"
    assert row["claim_category"] == "damaged_package"
