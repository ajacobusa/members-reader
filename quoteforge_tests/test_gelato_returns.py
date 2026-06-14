"""Gelato-accurate claim & 'return' handling. Ground truth from gelato.com:
Gelato accepts NO physical returns and gives NO return address - covered issues
are resolved by a complimentary REPRINT (claim via the Dashboard 'Report
Problem' flow, photos mandatory, 30-day window). So the customer is told to KEEP
the item, never to ship it back. Returned-to-sender (wrong address/rejection)
gets no refund; the mitigation is a new order within 30 days + a product-price
refund request (shipping not refunded)."""


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _order(db, **kw):
    base = {"order_id": "QF-1", "etsy_order_id": "1", "recipient_name": "A",
            "occasion": "B"}
    db.create_order(base)
    db.update_order("QF-1", **kw)
    return db.get_order("QF-1")


def test_covered_claim_package_requires_photos_and_targets_dashboard(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from datetime import datetime, timedelta
    o = _order(db, status="delivered", delivery_confirmed=1, vendor="gelato",
               gelato_order_id="GEL9",
               delivered_at=(datetime.now() - timedelta(days=2)).isoformat())
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    pkg = build_claim_package(o, "damaged")
    assert pkg["gelato_covered"] is True
    assert pkg["resolution"] == "reprint"
    assert pkg["gelato_order_ref"] == "GEL9"
    assert "GEL9" in pkg["dashboard_url"]               # deep link to Report Problem
    # Mandatory Gelato photos for damage: product + packaging + shipping label.
    assert set(pkg["missing_photos"]) == {"product", "packaging", "shipping_label"}
    assert pkg["ready_to_file"] is False                # photos missing -> not ready


def test_claim_ready_when_photos_present_and_in_window(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from datetime import datetime, timedelta
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1",
               delivered_at=(datetime.now() - timedelta(days=3)).isoformat())
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    pkg = build_claim_package(o, "printing_error",
                              photos=["product", "shipping_label"])
    assert pkg["missing_photos"] == [] and pkg["ready_to_file"] is True


def test_customer_message_says_keep_item_never_return(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1")
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    msg = build_claim_package(o, "damaged")["customer_message"].lower()
    assert "replacement" in msg
    assert "return" not in msg or "no need to return" in msg or "don't" in msg
    assert "keep" in msg or "recycle" in msg or "no need to return" in msg


def test_past_30_day_gelato_window_not_coverable(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from datetime import datetime, timedelta
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1",
               delivered_at=(datetime.now() - timedelta(days=40)).isoformat())
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    pkg = build_claim_package(o, "damaged", photos=["product", "packaging", "shipping_label"])
    assert pkg["within_gelato_window"] is False
    assert pkg["ready_to_file"] is False                # past Gelato's 30 days


def test_customer_error_not_gelato_covered(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1")
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    pkg = build_claim_package(o, "wrong_personalization")
    assert pkg["gelato_covered"] is False
    assert pkg["resolution"] == "no_gelato_coverage"


def test_returned_to_sender_plan_no_refund_new_order_mitigation(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from datetime import datetime, timedelta
    o = _order(db, status="shipped", gelato_order_id="G1",
               estimated_delivery=(datetime.now() - timedelta(days=5)).date().isoformat())
    from quoteforge.fulfillment.gelato_returns import returned_to_sender_plan
    plan = returned_to_sender_plan(o)
    assert plan["refund_owed"] is False                 # Gelato gives no RTS refund
    assert plan["within_window"] is True                # within 30d of est delivery
    assert any("new order" in s.lower() for s in plan["mitigation"])
    assert any("shipping" in s.lower() for s in plan["mitigation"])


def test_record_claim_persists_status(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1")
    from quoteforge.fulfillment.gelato_returns import record_claim
    record_claim("QF-1", "damaged", "staged")
    row = db.get_order("QF-1")
    assert row["claim_status"] == "staged" and row["claim_category"] == "damaged"
    assert row["claim_filed_at"]
