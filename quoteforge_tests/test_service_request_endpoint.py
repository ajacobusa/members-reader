"""The /service-request Flask endpoint validates a customer return request
against the order record, documents it, and returns the individual-review
acknowledgement (auto-running intake_claim instead of the email fallback)."""
from datetime import datetime, timedelta

import pytest


def _seed(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    db.create_order({"order_id": "QF-1", "etsy_order_id": "E1",
                     "customer_email": "buyer@mail.com", "recipient_name": "A",
                     "occasion": "B"})
    db.update_order("QF-1", status="delivered", delivery_confirmed=1,
                    gelato_order_id="GEL9",
                    delivered_at=(datetime.now() - timedelta(days=2)).isoformat())
    return db


def test_service_request_endpoint_documents_and_acks(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.automation.webhook_server import app
    if app is None:
        pytest.skip("Flask not installed")
    client = app.test_client()
    resp = client.post("/service-request", data={
        "name": "A", "order_number": "E1", "email": "buyer@mail.com",
        "issue_type": "Damaged item", "description": "crushed corner",
        "consent": "1"}, content_type="multipart/form-data")
    assert resp.status_code == 200
    j = resp.get_json()
    assert "reviewed individually" in j["message"]
    assert j["order_matched"] is True
    # No photos sent -> damage needs product+packaging -> documented as more-info.
    assert j["recommended_status"] == "needs_more_info"
    assert db.get_order("QF-1")["claim_status"] == "needs_more_info"
    assert db.get_order("QF-1")["claim_category"] == "damaged_package"


def test_service_request_endpoint_unknown_order_still_acks(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from quoteforge.automation.webhook_server import app
    if app is None:
        pytest.skip("Flask not installed")
    resp = app.test_client().post("/service-request", data={
        "name": "X", "order_number": "NOPE", "email": "x@y.com",
        "issue_type": "Lost package", "description": "never came",
        "consent": "1"}, content_type="multipart/form-data")
    assert resp.status_code == 200
    j = resp.get_json()
    assert "reviewed individually" in j["message"]
    assert j["order_matched"] is False
