"""Delivered-address sanity check: compare the carrier's delivered location
(from the tracking checkpoint) with the order's ship-to. A country mismatch is
flagged for owner review (catches wrong-destination delivery)."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_carrier_detail_returns_status_and_location():
    payload = {"data": {"tracking": {"tag": "Delivered",
        "checkpoints": [{"tag": "InTransit", "country_iso3": "USA"},
                        {"tag": "Delivered", "country_iso3": "USA",
                         "state": "GA"}]}}}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json
            return json.dumps(payload).encode("utf-8")
    import quoteforge.config as cfg
    with patch.object(cfg, "TEST_MODE", False), \
         patch.object(cfg, "TRACKING_API_KEY", "k"), \
         patch.object(cfg, "TRACKING_API_PROVIDER", "aftership"), \
         patch("urllib.request.urlopen", return_value=_Resp()):
        from quoteforge.fulfillment.tracking_api import carrier_detail
        d = carrier_detail("1Z", "usps")
    assert d["status"] == "delivered"
    assert d["delivered_country"] in ("US", "USA")


def test_delivery_to_wrong_country_is_flagged(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "A1", "etsy_order_id": "E1",
                     "recipient_name": "A", "occasion": "B"})
    db.update_order("A1", vendor="gelato", vendor_order_id="G1",
                    status="shipped", tracking_number="1Z", country="US",
                    shipped_at=(datetime.now() - timedelta(days=3)).isoformat())
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")
    # Carrier confirms delivered, but in a DIFFERENT country than ship-to.
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z"}), \
         patch("quoteforge.fulfillment.tracking_api.carrier_detail",
               return_value={"status": "delivered", "delivered_country": "CA",
                             "delivered_state": ""}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "A1" in r["address_mismatch"]


def test_matching_country_not_flagged(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "A2", "etsy_order_id": "E2",
                     "recipient_name": "A", "occasion": "B"})
    db.update_order("A2", vendor="gelato", vendor_order_id="G2",
                    status="shipped", tracking_number="1Z2", country="US",
                    shipped_at=(datetime.now() - timedelta(days=3)).isoformat())
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z2"}), \
         patch("quoteforge.fulfillment.tracking_api.carrier_detail",
               return_value={"status": "delivered", "delivered_country": "US",
                             "delivered_state": "GA"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "A2" not in r["address_mismatch"]
    assert db.get_order("A2")["delivery_confirmed"] == 1
