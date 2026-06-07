"""Tests for the fulfillment tracking sync (order -> shipped/delivered)."""
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_sync_marks_shipped_and_pushes_to_etsy(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T1", "etsy_order_id": "E1",
                           "recipient_name": "Emma", "occasion": "Birthday"})
    db.update_order(oid, gelato_order_id="G1", status="in_production")
    pushed = {}
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z999"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               side_effect=lambda *a, **k: pushed.update(a=a, k=k) or {"status": "ok"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T1" in r["newly_shipped"] and "T1" in r["pushed_to_etsy"]
    assert db.get_order("T1")["tracking_number"] == "1Z999"
    assert db.get_order("T1")["status"] == "shipped"


def test_sync_marks_delivered(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T2", "etsy_order_id": "E2",
                           "recipient_name": "Sam", "occasion": "Graduation"})
    db.update_order(oid, gelato_order_id="G2", status="shipped",
                    tracking_number="1Z888")
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "delivered", "tracking_number": "1Z888"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T2" in r["delivered"] and db.get_order("T2")["status"] == "delivered"


def test_track_command_registered():
    from quoteforge import admin
    assert "track-orders" in admin.COMMANDS
