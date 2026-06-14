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


def test_normalize_recipient_iso_and_validity():
    from quoteforge.fulfillment.gelato_returns import normalize_recipient
    n = normalize_recipient({"name": "A", "address": "1 Main St", "city": "Atlanta",
                             "state": "ga", "postCode": "30301", "country": "usa"})
    assert n["valid"] is True
    assert n["recipient"]["country"] == "US" and n["recipient"]["state"] == "GA"
    bad = normalize_recipient({"name": "A", "country": "US"})
    assert bad["valid"] is False and "missing street address" in bad["issues"]


def test_route_order_blocks_incomplete_address(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "X", "vendor": "gelato", "gelato_product_uid": "u"},
                    recipient={"name": "A", "country": "US"},
                    artwork_url="https://x/art.png")
    assert r["status"] == "manual" and "address" in r["detail"].lower()


def test_validate_address_flags_missing_and_normalizes():
    from quoteforge.fulfillment.gelato_returns import validate_address
    ok = validate_address({"firstName": "A", "addressLine1": "1 Main St",
                           "city": "Atlanta", "state": "ga", "postCode": "30301",
                           "country": "usa"})
    assert ok["valid"] is True
    assert ok["normalized"]["country"] == "US"      # ISO-2 normalised
    assert ok["normalized"]["state"] == "GA"
    bad = validate_address({"firstName": "A", "city": "Atlanta", "country": "US"})
    assert bad["valid"] is False
    joined = " ".join(bad["issues"]).lower()
    assert "addressline1" in joined and "postcode" in joined


def test_prevent_rts_pushes_normalized_address_before_ship(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="in_production", gelato_order_id="G1")
    seen = {}
    monkeypatch.setattr(
        "quoteforge.automation.gelato_api.update_gelato_shipping_address",
        lambda gid, addr: seen.update(gid=gid, addr=addr) or {"status": "mock_updated"})
    from quoteforge.fulfillment.gelato_returns import prevent_rts
    res = prevent_rts(o, {"firstName": "A", "addressLine1": "1 Main St",
                          "city": "Atlanta", "state": "ga", "postCode": "30301",
                          "country": "usa"})
    assert res["updated"] is True
    assert seen["gid"] == "G1" and seen["addr"]["country"] == "US"


def test_prevent_rts_skips_after_ship(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="shipped", gelato_order_id="G1")
    from quoteforge.fulfillment.gelato_returns import prevent_rts
    res = prevent_rts(o, {"firstName": "A", "addressLine1": "1 Main St",
                          "city": "Atlanta", "state": "GA", "postCode": "30301",
                          "country": "US"})
    assert res["updated"] is False and "ship" in res["reason"].lower()


def test_prevent_rts_flags_incomplete_address_no_push(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="in_production", gelato_order_id="G1")
    from quoteforge.fulfillment.gelato_returns import prevent_rts
    res = prevent_rts(o, {"firstName": "A", "country": "US"})   # missing line/city/zip
    assert res["updated"] is False and res["issues"]


def test_claim_auto_attaches_stored_customer_photos(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from datetime import datetime, timedelta
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1",
               delivered_at=(datetime.now() - timedelta(days=2)).isoformat())
    from quoteforge.fulfillment.gelato_returns import (record_claim_photos,
                                                      build_claim_package)
    record_claim_photos("QF-1", ["product", "packaging", "shipping_label"])
    o = db.get_order("QF-1")
    pkg = build_claim_package(o, "damaged")            # no photos passed in
    assert pkg["missing_photos"] == [] and pkg["ready_to_file"] is True
    assert "product" in pkg["auto_attached"]


def test_claim_attaches_approved_design_reference(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1",
               artwork_url="https://x/art.png")
    from quoteforge.fulfillment.gelato_returns import build_claim_package
    pkg = build_claim_package(o, "printing_error", photos=["product", "shipping_label"])
    assert pkg["approved_design_ref"] == "https://x/art.png"


def test_record_claim_persists_status(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    o = _order(db, status="delivered", delivery_confirmed=1, gelato_order_id="G1")
    from quoteforge.fulfillment.gelato_returns import record_claim
    record_claim("QF-1", "damaged", "staged")
    row = db.get_order("QF-1")
    assert row["claim_status"] == "staged" and row["claim_category"] == "damaged"
    assert row["claim_filed_at"]
