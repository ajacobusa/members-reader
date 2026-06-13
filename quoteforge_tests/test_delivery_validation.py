"""Delivery is validated end to end: real (carrier-confirmed) delivery is
distinguished from a timer ASSUMPTION, the buyer shipped-notification retries
until it succeeds, stuck orders raise an alarm, and vendor errors are logged
(not silently swallowed)."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_gelato_delivery_is_confirmed(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "D1", "etsy_order_id": "E1",
                           "recipient_name": "A", "occasion": "Birthday"})
    db.update_order(oid, gelato_order_id="G1", status="in_production")
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "delivered", "tracking_number": "1Z1"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "ok"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    o = db.get_order("D1")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 1
    assert "D1" in r["delivered_confirmed"]


def test_printful_assumed_delivery_is_not_confirmed(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "D2", "etsy_order_id": "E2",
                           "recipient_name": "B", "occasion": "Wedding"})
    old = (datetime.now() - timedelta(days=20)).isoformat()
    db.update_order(oid, vendor="printful", gelato_order_id="44",
                    status="shipped", tracking_number="1Z2", shipped_at=old)
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    r = sync_tracking()
    o = db.get_order("D2")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 0
    assert "D2" in r["delivered_assumed"]


def test_buyer_notification_retries_after_failed_push(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "D3", "etsy_order_id": "E3",
                           "recipient_name": "C", "occasion": "Anniversary"})
    db.update_order(oid, gelato_order_id="G3", status="in_production")
    from quoteforge.automation import fulfillment_tracker as ft
    # First run: tracking appears but the Etsy push FAILS -> not marked notified.
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z3"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               side_effect=RuntimeError("etsy down")):
        ft.sync_tracking()
    assert (db.get_order("D3").get("buyer_notified") or 0) == 0
    # Second run: push succeeds -> buyer finally notified (the push RETRIED
    # even though tracking was already known).
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z3"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "ok"}) as push:
        r = ft.sync_tracking()
    assert push.called and db.get_order("D3")["buyer_notified"] == 1
    assert "D3" in r["pushed_to_etsy"]


def test_stuck_order_is_flagged(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "D4", "recipient_name": "D",
                           "occasion": "New Baby"})
    old = (datetime.now() - timedelta(days=30)).isoformat()
    db.update_order(oid, vendor="printify", gelato_order_id="P4",
                    status="in_production", created_at=old)
    # Vendor never returns tracking (mock returns none).
    with patch("quoteforge.fulfillment.printify.get_order_status",
               return_value={"status": "unknown", "tracking_number": ""}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "D4" in r["stuck"]


def test_vendor_poll_error_is_logged_not_swallowed(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "D5", "recipient_name": "E",
                           "occasion": "Graduation"})
    db.update_order(oid, vendor="printify", gelato_order_id="P5",
                    status="in_production")
    with patch("quoteforge.fulfillment.printify.get_order_status",
               side_effect=RuntimeError("boom")):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert r["errors"] >= 1
    log = db.get_pipeline_log("D5")
    assert any(e["status"] == "error" for e in log)


def test_assumed_delivery_backfills_missing_shipped_at(tmp_path, monkeypatch):
    """A tracked Printify order with no shipped_at must not freeze forever -
    the ship date is backfilled so the assumed-delivery clock can start."""
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "D6", "recipient_name": "F",
                           "occasion": "Christmas"})
    db.update_order(oid, vendor="printify", gelato_order_id="P6",
                    status="shipped", tracking_number="1Z6")  # no shipped_at
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    sync_tracking()
    assert db.get_order("D6").get("shipped_at")
