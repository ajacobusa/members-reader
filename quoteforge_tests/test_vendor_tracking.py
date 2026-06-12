"""Printify/Printful integration — status polling, auth checks, vendor-aware
tracking sync (mirrors the Gelato/Etsy pattern in fulfillment_tracker)."""
import io
import json
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _fake_http(payload: dict):
    """A urlopen replacement returning the given JSON payload."""
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return lambda *a, **k: _Resp(json.dumps(payload).encode("utf-8"))


# ── Printify adapter ─────────────────────────────────────────────────

def test_printify_status_is_mock_in_test_mode(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    from quoteforge.fulfillment.printify import get_order_status
    s = get_order_status("P1")
    assert s["mock"] is True and s["vendor"] == "printify"
    assert s["tracking_number"] == ""


def test_printify_status_maps_fulfilled_to_shipped(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.config.PRINTIFY_API_KEY", "k")
    monkeypatch.setattr("quoteforge.config.PRINTIFY_SHOP_ID", "s1")
    payload = {"id": "P1", "status": "fulfilled",
               "shipments": [{"carrier": "usps", "number": "9400111",
                              "url": "https://t/9400111"}]}
    with patch("urllib.request.urlopen", new=_fake_http(payload)):
        from quoteforge.fulfillment.printify import get_order_status
        s = get_order_status("P1")
    assert s["status"] == "shipped"
    assert s["tracking_number"] == "9400111"
    assert s["tracking_url"] == "https://t/9400111"
    assert s["carrier"] == "usps"


def test_verify_printify_auth_without_key(monkeypatch):
    monkeypatch.setattr("quoteforge.config.PRINTIFY_API_KEY", "")
    monkeypatch.setattr("quoteforge.config.PRINTIFY_SHOP_ID", "")
    from quoteforge.fulfillment.printify import verify_printify_auth
    r = verify_printify_auth()
    assert r["ok"] is False and "not set" in r["detail"]


# ── Printful adapter ─────────────────────────────────────────────────

def test_printful_status_is_mock_in_test_mode(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    from quoteforge.fulfillment.printful import get_order_status
    s = get_order_status("42")
    assert s["mock"] is True and s["vendor"] == "printful"
    assert s["tracking_number"] == ""


def test_printful_status_maps_fulfilled_to_shipped(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.config.PRINTFUL_API_KEY", "k")
    payload = {"result": {"id": 42, "status": "fulfilled",
                          "shipments": [{"carrier": "FEDEX",
                                         "tracking_number": "7777",
                                         "tracking_url": "https://t/7777"}]}}
    with patch("urllib.request.urlopen", new=_fake_http(payload)):
        from quoteforge.fulfillment.printful import get_order_status
        s = get_order_status("42")
    assert s["status"] == "shipped"
    assert s["tracking_number"] == "7777"
    assert s["tracking_url"] == "https://t/7777"
    assert s["carrier"] == "FEDEX"


def test_verify_printful_auth_without_key(monkeypatch):
    monkeypatch.setattr("quoteforge.config.PRINTFUL_API_KEY", "")
    from quoteforge.fulfillment.printful import verify_printful_auth
    r = verify_printful_auth()
    assert r["ok"] is False and "not set" in r["detail"]


# ── Vendor-aware tracking sync (same flow Etsy/Gelato uses) ──────────

def test_sync_tracks_printify_order_and_pushes_to_etsy(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T3", "etsy_order_id": "E3",
                           "recipient_name": "Liam", "occasion": "Wedding"})
    db.update_order(oid, vendor="printify", gelato_order_id="P9",
                    status="in_production")
    pushed = {}
    with patch("quoteforge.fulfillment.printify.get_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z777",
                             "carrier": "usps"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               side_effect=lambda *a, **k: pushed.update(a=a, k=k) or {"status": "ok"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T3" in r["newly_shipped"] and "T3" in r["pushed_to_etsy"]
    assert db.get_order("T3")["tracking_number"] == "1Z777"
    assert db.get_order("T3")["status"] == "shipped"


def test_printful_order_assumed_delivered_after_window(tmp_path, monkeypatch):
    """Printify/Printful APIs never report 'delivered', so a shipped order with
    tracking is assumed delivered after the safety window - WITHOUT polling."""
    from datetime import datetime, timedelta
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T4", "etsy_order_id": "E4",
                           "recipient_name": "Ava", "occasion": "Anniversary"})
    old = (datetime.now() - timedelta(days=20)).isoformat()
    db.update_order(oid, vendor="printful", gelato_order_id="44",
                    status="shipped", tracking_number="1Z666", shipped_at=old)

    def _no_poll(*a, **k):
        raise AssertionError("vendor API must not be polled once tracking is known")
    with patch("quoteforge.fulfillment.printful.get_order_status", _no_poll):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T4" in r["delivered"]
    o = db.get_order("T4")
    assert o["status"] == "delivered" and o["delivered_at"]


def test_recently_shipped_printify_order_not_repolled(tmp_path, monkeypatch):
    """Once tracking is on a Printify order there is nothing new the API can
    report - no poll, and no premature 'delivered' inside the window."""
    from datetime import datetime, timedelta
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T4b", "etsy_order_id": "E4b",
                           "recipient_name": "Zoe", "occasion": "Birthday"})
    recent = (datetime.now() - timedelta(days=2)).isoformat()
    db.update_order(oid, vendor="printify", gelato_order_id="P2",
                    status="shipped", tracking_number="1Z222", shipped_at=recent)
    polls = []
    with patch("quoteforge.fulfillment.printify.get_order_status",
               side_effect=lambda *a, **k: polls.append(1) or
               {"status": "shipped", "tracking_number": "1Z222"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert not polls, "vendor API was polled although tracking is already known"
    assert "T4b" not in r["delivered"]
    assert db.get_order("T4b")["status"] == "shipped"


def test_empty_carrier_falls_back_to_other(tmp_path, monkeypatch):
    """A present-but-empty carrier from Printify/Printful must not reach Etsy
    as carrier_name='' (Etsy rejects it) - it falls back to 'other'."""
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T6", "etsy_order_id": "E6",
                           "recipient_name": "Kai", "occasion": "Wedding"})
    db.update_order(oid, vendor="printify", gelato_order_id="P6",
                    status="in_production")
    pushed = {}
    with patch("quoteforge.fulfillment.printify.get_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z000",
                             "carrier": ""}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               side_effect=lambda *a, **k: pushed.update(k=k) or {"status": "ok"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        sync_tracking()
    assert pushed["k"].get("carrier_name") == "other"


def test_non_etsy_order_still_gets_shipped_at(tmp_path, monkeypatch):
    """A direct/manual-channel order (no etsy_order_id) must still be counted
    as newly shipped and get its shipped_at stamped (no Etsy push attempted)."""
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T7",
                           "recipient_name": "Joy", "occasion": "New Baby"})
    db.update_order(oid, vendor="printful", gelato_order_id="77",
                    status="in_production")
    with patch("quoteforge.fulfillment.printful.get_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z111"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T7" in r["newly_shipped"] and "T7" not in r["pushed_to_etsy"]
    assert db.get_order("T7")["shipped_at"]


def test_printify_tracking_found_in_later_shipment(monkeypatch):
    """Partially-fulfilled orders may carry tracking on a later shipment -
    scan all shipments instead of blindly taking index 0 (Gelato parity)."""
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.config.PRINTIFY_API_KEY", "k")
    monkeypatch.setattr("quoteforge.config.PRINTIFY_SHOP_ID", "s1")
    payload = {"id": "P1", "status": "partially-fulfilled",
               "shipments": [{"carrier": "usps", "number": "", "url": ""},
                             {"carrier": "ups", "number": "1Z9",
                              "url": "https://t/1Z9"}]}
    with patch("urllib.request.urlopen", new=_fake_http(payload)):
        from quoteforge.fulfillment.printify import get_order_status
        s = get_order_status("P1")
    assert s["tracking_number"] == "1Z9" and s["carrier"] == "ups"


def test_printful_tracking_found_in_later_shipment(monkeypatch):
    """Same multi-shipment scan for Printful's tracking_number field."""
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.config.PRINTFUL_API_KEY", "k")
    payload = {"result": {"id": 42, "status": "partial",
                          "shipments": [{"carrier": "x", "tracking_number": ""},
                                        {"carrier": "FEDEX",
                                         "tracking_number": "7778",
                                         "tracking_url": "https://t/7778"}]}}
    with patch("urllib.request.urlopen", new=_fake_http(payload)):
        from quoteforge.fulfillment.printful import get_order_status
        s = get_order_status("42")
    assert s["tracking_number"] == "7778" and s["carrier"] == "FEDEX"


def test_verify_auth_reports_auth_rejected_on_401(monkeypatch):
    """A 401/403 must produce the actionable 'auth rejected ... check key'
    detail (Gelato parity), not a raw HTTPError repr."""
    import urllib.error
    monkeypatch.setattr("quoteforge.config.PRINTIFY_API_KEY", "bad")
    monkeypatch.setattr("quoteforge.config.PRINTIFY_SHOP_ID", "s1")
    monkeypatch.setattr("quoteforge.config.PRINTFUL_API_KEY", "bad")

    def _raise_401(*a, **k):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", None, None)
    from quoteforge.fulfillment.printify import verify_printify_auth
    from quoteforge.fulfillment.printful import verify_printful_auth
    with patch("urllib.request.urlopen", _raise_401):
        for r in (verify_printify_auth(), verify_printful_auth()):
            assert r["ok"] is False
            assert "auth rejected (HTTP 401)" in r["detail"]


def test_no_redundant_db_write_when_tracking_unchanged(tmp_path, monkeypatch):
    """Re-polling a gelato order whose tracking is already stored must not
    rewrite the row every 6 hours (the 'first appearance' contract)."""
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T8", "etsy_order_id": "E8",
                           "recipient_name": "Ben", "occasion": "Graduation"})
    db.update_order(oid, gelato_order_id="G8", status="shipped",
                    tracking_number="1Z444")
    writes = []
    real_update = db.update_order
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z444"}), \
         patch("quoteforge.db.database.update_order",
               side_effect=lambda *a, **k: writes.append(k) or real_update(*a, **k)):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        sync_tracking()
    assert not writes, f"unexpected DB writes: {writes}"


def test_sync_still_tracks_gelato_orders(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T5", "etsy_order_id": "E5",
                           "recipient_name": "Mia", "occasion": "Birthday"})
    db.update_order(oid, gelato_order_id="G5", status="in_production")
    with patch("quoteforge.automation.gelato_api.get_gelato_order_status",
               return_value={"status": "shipped", "tracking_number": "1Z555"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "ok"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T5" in r["newly_shipped"]
    assert db.get_order("T5")["tracking_number"] == "1Z555"


# ── Preflight visibility ─────────────────────────────────────────────

def test_preflight_reports_printify_and_printful_keys():
    from quoteforge.preflight import check_config
    names = [r.name for r in check_config()]
    assert "PRINTIFY_API_KEY" in names
    assert "PRINTFUL_API_KEY" in names
