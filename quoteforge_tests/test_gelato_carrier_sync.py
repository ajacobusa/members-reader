"""Gelato tracking sync with CARRIER-confirmed delivery: Gelato generates the
tracking number, the CARRIER reports delivered. A Gelato order shipped with
tracking is confirmed delivered by polling the carrier - not by a timer, and
not stuck forever waiting for Gelato to (maybe never) report 'delivered'."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_gelato_carrier_confirms_delivery(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "G1", "etsy_order_id": "E1",
                           "recipient_name": "A", "occasion": "B"})
    db.update_order(oid, vendor="gelato", gelato_order_id="GEL9",
                    status="in_production")
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")
    # Gelato reports SHIPPED (not delivered) with a tracking number...
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z",
                             "carrier": "usps"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "ok"}), \
         patch("quoteforge.fulfillment.tracking_api.carrier_detail",
               return_value={"status": "delivered", "delivered_country": "", "delivered_state": ""}):       # ...carrier says DELIVERED
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    o = db.get_order("G1")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 1
    assert "G1" in r["delivered_confirmed"]


def test_gelato_without_carrier_api_does_not_falsely_deliver(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "G2", "etsy_order_id": "E2",
                           "recipient_name": "B", "occasion": "C"})
    db.update_order(oid, vendor="gelato", gelato_order_id="GEL8",
                    status="shipped", tracking_number="1Z8",
                    shipped_at=(datetime.now() - timedelta(days=30)).isoformat())
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "")   # no carrier API
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z8"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        sync_tracking()
    # No timer for Gelato - it stays shipped until truly confirmed (no false +).
    assert db.get_order("G2")["status"] == "shipped"


def test_gelato_api_extracts_carrier_and_eta(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k")
    payload = {"fulfillmentStatus": "shipped", "items": [{"fulfillments": [{
        "trackingNumber": "1Z", "trackingUrl": "http://t/1Z",
        "shipmentMethodName": "USPS Priority",
        "expectedDeliveryDate": "2026-06-20"}]}]}

    class _R(bytes):
        pass
    import io

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    import json
    with patch("requests.get") as rg:
        rg.return_value.json.return_value = payload
        rg.return_value.raise_for_status.return_value = None
        from quoteforge.automation.gelato_api import get_gelato_order_status
        s = get_gelato_order_status("GEL9")
    assert s["carrier"] == "USPS Priority"
    assert s["estimated_delivery"] == "2026-06-20"
