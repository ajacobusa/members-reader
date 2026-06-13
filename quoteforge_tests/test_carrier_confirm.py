"""Carrier-confirmed delivery: when a tracking API is configured, a REAL
delivered scan confirms delivery (delivery_confirmed=1); an in-transit scan
keeps the order shipped (never falsely assume a delayed parcel arrived).
Without the API, the 14-day timer assumption still applies."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _shipped(db, oid, days_ago):
    db.create_order({"order_id": oid, "recipient_name": "A", "occasion": "B"})
    old = (datetime.now() - timedelta(days=days_ago)).isoformat()
    db.update_order(oid, vendor="printful", gelato_order_id="V",
                    status="shipped", tracking_number="1Z9", shipped_at=old)


def test_carrier_delivered_scan_confirms(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _shipped(db, "C1", 3)                         # only 3 days - timer wouldn't fire
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")
    with patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value="delivered"):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    o = db.get_order("C1")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 1
    assert "C1" in r["delivered_confirmed"]


def test_carrier_in_transit_keeps_shipped_even_past_timer(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _shipped(db, "C2", 30)                        # past 14d timer
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")
    with patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value="in_transit"):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        sync_tracking()
    o = db.get_order("C2")
    assert o["status"] == "shipped"               # carrier authoritative - not delivered


def test_no_api_falls_back_to_timer(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _shipped(db, "C3", 20)                         # past 14d, no API
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "")
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    r = sync_tracking()
    o = db.get_order("C3")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 0
    assert "C3" in r["delivered_assumed"]


def test_tracking_api_disabled_returns_none(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "")
    from quoteforge.fulfillment.tracking_api import carrier_status
    assert carrier_status("1Z9", "ups") is None
