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


def test_sync_marks_printful_order_delivered(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "T4", "etsy_order_id": "E4",
                           "recipient_name": "Ava", "occasion": "Anniversary"})
    db.update_order(oid, vendor="printful", gelato_order_id="44",
                    status="shipped", tracking_number="1Z666")
    with patch("quoteforge.fulfillment.printful.get_order_status",
               return_value={"status": "delivered", "tracking_number": "1Z666"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        r = sync_tracking()
    assert "T4" in r["delivered"]
    assert db.get_order("T4")["status"] == "delivered"


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
