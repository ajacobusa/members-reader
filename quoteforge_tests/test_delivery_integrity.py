"""Delivery integrity: 'delivered' is not automatically problem-free. Exception
states never confirm delivery; the review request is suppressed on dispute /
refund / cancellation / do-not-request; owner manual overrides are honored."""
from datetime import datetime, timedelta


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _delivered(db, oid, **extra):
    db.create_order({"order_id": oid, "customer_email": f"{oid}@b.com",
                     "recipient_name": "A", "occasion": "B"})
    old = (datetime.now() - timedelta(days=10)).isoformat()
    db.update_order(oid, status="delivered", delivery_confirmed=1,
                    delivered_at=old, **extra)


def test_only_delivered_tag_confirms_failed_states_are_exceptions():
    from quoteforge.fulfillment.tracking_api import _AFTERSHIP_MAP
    confirms = [k for k, v in _AFTERSHIP_MAP.items() if v == "delivered"]
    assert confirms == ["Delivered"]
    # A failed delivery / return-to-sender must be an EXCEPTION, never confirm.
    assert _AFTERSHIP_MAP.get("AttemptFail") == "exception"
    assert _AFTERSHIP_MAP.get("Exception") == "exception"
    for state in ("InTransit", "OutForDelivery", "AvailableForPickup",
                  "InfoReceived"):
        assert _AFTERSHIP_MAP.get(state) != "delivered"
    # Out-for-delivery is the last pre-arrival state - it normalizes to in_transit
    # (the "did it arrive?" decision only flips on a literal Delivered scan).
    assert _AFTERSHIP_MAP.get("OutForDelivery") == "in_transit"


def test_review_suppressed_when_disputed(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _delivered(db, "D1", delivery_disputed=1)
    from quoteforge.etsy.delight_loop import delight_due
    assert not any(d["order_id"] == "D1" for d in delight_due(db.get_all_orders(50)))


def test_review_suppressed_for_refunded_and_cancelled(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _delivered(db, "D2")
    db.update_order("D2", status="refunded")
    _delivered(db, "D3")
    db.update_order("D3", status="cancelled")
    from quoteforge.etsy.delight_loop import delight_due
    ids = [d["order_id"] for d in delight_due(db.get_all_orders(50))]
    assert "D2" not in ids and "D3" not in ids


def test_review_suppressed_by_do_not_request_flag(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _delivered(db, "D4", do_not_request_review=1)
    from quoteforge.etsy.delight_loop import delight_due
    assert not any(d["order_id"] == "D4" for d in delight_due(db.get_all_orders(50)))


def test_mark_delivery_disputed_sets_flag(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _delivered(db, "D5")
    from quoteforge.automation.fulfillment_tracker import mark_delivery_disputed
    mark_delivery_disputed("D5", reason="Etsy case opened")
    o = db.get_order("D5")
    assert o["delivery_disputed"] == 1


def test_manual_delivery_confirmed_makes_review_eligible(tmp_path, monkeypatch):
    """An owner manual confirmation counts as a confirmed delivery for the
    review flow even with no carrier scan."""
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "D6", "customer_email": "d6@b.com",
                     "recipient_name": "A", "occasion": "B"})
    old = (datetime.now() - timedelta(days=10)).isoformat()
    db.update_order("D6", status="shipped", manual_delivery_confirmed=1,
                    delivered_at=old)
    from quoteforge.etsy.delight_loop import delight_due
    assert any(d["order_id"] == "D6" for d in delight_due(db.get_all_orders(50)))
