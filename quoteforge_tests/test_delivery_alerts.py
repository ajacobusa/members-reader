"""Operational delivery alerts surfaced by sync_tracking:
 - tracking_missing: submitted to the vendor but no tracking after 24-48h.
 - stale_in_transit: shipped but in transit past the destination SLA
   (domestic 7-10d, international 14-21d) - flag before the customer complains."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_tracking_missing_flagged_after_window(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T1", "recipient_name": "A",
                           "occasion": "B"})
    old = (datetime.now() - timedelta(hours=48)).isoformat()
    db.update_order(oid, vendor="gelato", gelato_order_id="G1",
                    vendor_order_id="G1", status="in_production", created_at=old)
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "in_production", "tracking_number": ""}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T1" in r["tracking_missing"]


def test_fresh_order_not_flagged_missing(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T2", "recipient_name": "A",
                           "occasion": "B"})
    db.update_order(oid, vendor="gelato", gelato_order_id="G2",
                    vendor_order_id="G2", status="in_production")  # just now
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "in_production", "tracking_number": ""}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T2" not in r["tracking_missing"]


def test_stale_in_transit_domestic_vs_international(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    # Domestic, shipped 12 days ago -> stale (limit 10).
    a = db.create_order({"order_id": "S1", "recipient_name": "A", "occasion": "B"})
    db.update_order(a, vendor="gelato", gelato_order_id="GA", vendor_order_id="GA",
                    status="shipped", tracking_number="1Z", country="US",
                    shipped_at=(datetime.now() - timedelta(days=12)).isoformat())
    # International, shipped 12 days ago -> NOT stale yet (limit 21).
    b = db.create_order({"order_id": "S2", "recipient_name": "B", "occasion": "C"})
    db.update_order(b, vendor="gelato", gelato_order_id="GB", vendor_order_id="GB",
                    status="shipped", tracking_number="1Z2", country="AU",
                    shipped_at=(datetime.now() - timedelta(days=12)).isoformat())
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z"}), \
         patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value=None):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "S1" in r["stale_in_transit"]
    assert "S2" not in r["stale_in_transit"]
