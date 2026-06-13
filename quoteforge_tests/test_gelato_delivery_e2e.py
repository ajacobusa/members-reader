"""End-to-end Gelato tracking -> carrier-confirmed delivery -> review.

Proves the full operational chain: Gelato ships + generates tracking ->
tracking pushed to the Etsy buyer -> carrier reports delivered -> order is
carrier-confirmed -> the review/delight sequence becomes eligible. Every field
the roadmap says to store is asserted present."""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_gelato_full_lifecycle_to_confirmed_delivery(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-1", "etsy_order_id": "12345",
                     "customer_email": "a@b.com", "recipient_name": "Ann",
                     "occasion": "Birthday"})
    db.update_order("QF-1", vendor="gelato", gelato_order_id="GEL987",
                    vendor_order_id="GEL987", status="in_production")
    monkeypatch.setattr("quoteforge.config.TRACKING_API_KEY", "k")

    from quoteforge.automation.fulfillment_tracker import sync_tracking
    # --- Sync 1: Gelato has shipped, generated tracking + carrier + ETA ---
    gel_shipped = {"status": "shipped", "tracking_number": "9400111",
                   "carrier": "USPS", "estimated_delivery": "2026-06-20"}
    pushes = []
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value=gel_shipped), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               side_effect=lambda *a, **k: pushes.append((a, k)) or {"status": "ok"}), \
         patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value="in_transit"):
        r1 = sync_tracking()
    o = db.get_order("QF-1")
    assert o["status"] == "shipped" and o["tracking_number"] == "9400111"
    assert o["carrier"] == "USPS" and o["estimated_delivery"] == "2026-06-20"
    assert "QF-1" in r1["newly_shipped"] and "QF-1" in r1["pushed_to_etsy"]
    assert o["buyer_notified"] == 1                  # tracking pushed to Etsy buyer
    assert pushes and pushes[0][0][0] == "12345"     # pushed to the Etsy receipt

    # --- Sync 2: carrier reports DELIVERED -> carrier-confirmed ---
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value=gel_shipped), \
         patch("quoteforge.fulfillment.tracking_api.carrier_status",
               return_value="delivered"):
        r2 = sync_tracking()
    o = db.get_order("QF-1")
    assert o["status"] == "delivered" and o["delivery_confirmed"] == 1
    assert o["delivered_at"] and "QF-1" in r2["delivered_confirmed"]

    # Every roadmap field is stored.
    for f in ("etsy_order_id", "vendor_order_id", "tracking_number", "carrier",
              "shipped_at", "estimated_delivery", "delivered_at",
              "delivery_confirmed"):
        assert o.get(f) not in (None, ""), f

    # --- well past the lead: the review/delight touch is eligible ---
    old = (datetime.now() - timedelta(days=10)).isoformat()
    db.update_order("QF-1", delivered_at=old, updated_at=old)
    from quoteforge.etsy.delight_loop import delight_due
    due = delight_due(db.get_all_orders(50))
    assert any(d["order_id"] == "QF-1" for d in due)
