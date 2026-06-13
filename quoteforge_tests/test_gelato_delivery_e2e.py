"""End-to-end Gelato lifecycle: route -> poll -> persist -> carrier-confirmed
delivery -> review. Proves the full operational chain AND that the system does
NOT mark an order received too early (in_transit first, then delivered)."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


GOOD_ADDR = {"name": "Ann", "address": "1 Main St", "city": "Atlanta",
             "state": "GA", "postCode": "30301", "country": "US"}


def test_gelato_e2e_route_to_carrier_confirmed_delivery(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)   # mock Gelato create
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-1", "etsy_order_id": "12345",
                     "customer_email": "a@b.com", "recipient_name": "Ann",
                     "occasion": "Birthday"})

    # 1-2. Etsy order is ROUTED to Gelato and the gelato order id is SAVED.
    from quoteforge.fulfillment.router import route_order
    resp = route_order(
        {"order_id": "QF-1", "vendor": "gelato", "gelato_product_uid": "uid-1"},
        recipient=GOOD_ADDR, artwork_url="https://x/art.png")
    assert resp["status"] == "submitted" and resp["vendor"] == "gelato"
    gid = resp["id"]
    assert gid, "Gelato did not return an order id"
    db.update_order("QF-1", vendor="gelato", gelato_order_id=gid,
                    vendor_order_id=gid, status="in_production")
    assert db.get_order("QF-1")["vendor_order_id"] == gid

    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    # 3-5. Poll reaches Gelato; Gelato returns carrier/tracking/ETA; persisted.
    #      Carrier says IN_TRANSIT -> the order must NOT be marked delivered.
    gel = {"status": "shipped", "tracking_number": "9400111",
           "carrier": "USPS", "estimated_delivery": "2026-06-20"}
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value=gel), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "ok"}), \
         patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value="in_transit"):
        r1 = sync_tracking()
    o = db.get_order("QF-1")
    assert o["tracking_number"] == "9400111" and o["carrier"] == "USPS"
    assert o["estimated_delivery"] == "2026-06-20" and o["shipped_at"]
    # NOT received too early:
    assert o["status"] == "shipped" and (o["delivery_confirmed"] or 0) == 0
    assert "QF-1" not in r1["delivered_confirmed"]
    assert "QF-1" not in r1["delivered_assumed"]
    assert "QF-1" in r1["pushed_to_etsy"]              # tracking pushed to Etsy buyer

    # Review/delight must NOT be eligible while only shipped (not delivered).
    from quoteforge.etsy.delight_loop import delight_due
    assert not any(d["order_id"] == "QF-1" for d in delight_due(db.get_all_orders(50)))

    # 6-7. Carrier later reports DELIVERED -> carrier-confirmed.
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value=gel), \
         patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value="delivered"):
        r2 = sync_tracking()
    o = db.get_order("QF-1")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 1
    assert o["delivered_at"] and "QF-1" in r2["delivered_confirmed"]
    for f in ("etsy_order_id", "vendor_order_id", "tracking_number", "carrier",
              "shipped_at", "estimated_delivery", "delivered_at"):
        assert o.get(f), f

    # 8. Review/delight is eligible only AFTER confirmed delivery + the lead.
    old = (datetime.now() - timedelta(days=10)).isoformat()
    db.update_order("QF-1", delivered_at=old)
    assert any(d["order_id"] == "QF-1" for d in delight_due(db.get_all_orders(50)))


def test_review_starts_after_safe_assumed_fallback(tmp_path, monkeypatch):
    """The OTHER branch: Printify/Printful with no carrier API. The order is
    assumed delivered after the timer (delivery_confirmed=0), and the review
    flow becomes eligible only after the extra assumed-delivery buffer."""
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-2", "etsy_order_id": "222",
                     "customer_email": "c@b.com", "recipient_name": "B",
                     "occasion": "Wedding"})
    shipped = (datetime.now() - timedelta(days=20)).isoformat()
    db.update_order("QF-2", vendor="printful", vendor_order_id="P9",
                    status="shipped", tracking_number="1Z", shipped_at=shipped)
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "")   # no carrier API
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    r = sync_tracking()
    o = db.get_order("QF-2")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 0
    assert "QF-2" in r["delivered_assumed"]
    # Assumed delivery -> review waits the extra buffer; well past it -> eligible.
    from quoteforge.etsy.delight_loop import delight_due
    db.update_order("QF-2", delivered_at=(datetime.now() - timedelta(days=20)).isoformat())
    assert any(d["order_id"] == "QF-2" for d in delight_due(db.get_all_orders(50)))
