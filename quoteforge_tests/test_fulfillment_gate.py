"""Every order is validated before money is spent at the print vendor - on
BOTH the auto-approve and the manual-proof paths (was: validator only on the
manual path, so auto-approved/marketplace orders shipped unverified)."""
from unittest.mock import patch

from PIL import Image


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    import quoteforge.automation.pipeline_orchestrator as po
    monkeypatch.setattr(po, "OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


GOOD_ADDR = {"name": "Ann", "address": "1 St", "city": "Atlanta",
             "state": "GA", "postCode": "30301", "country": "US"}


def test_gate_passes_complete_print_order():
    from quoteforge.automation.pipeline_orchestrator import validate_for_fulfillment
    r = validate_for_fulfillment(
        {"product_type": "print", "print_quality": "approve"},
        GOOD_ADDR, "uid-123", "https://x/y.png")
    assert r["ok"], r["issues"]


def test_gate_holds_incomplete_address():
    from quoteforge.automation.pipeline_orchestrator import validate_for_fulfillment
    r = validate_for_fulfillment(
        {"product_type": "print"},
        {"name": "Ann", "country": "US"}, "uid", "https://x/y.png")
    assert not r["ok"]
    assert any("address" in i for i in r["issues"])


def test_gate_holds_rejected_quality():
    from quoteforge.automation.pipeline_orchestrator import validate_for_fulfillment
    r = validate_for_fulfillment(
        {"product_type": "print", "print_quality": "reject"},
        GOOD_ADDR, "uid", "https://x/y.png")
    assert not r["ok"]


def test_gate_skips_digital_products():
    """A digital download has no shipping - the physical gate must not block it."""
    from quoteforge.automation.pipeline_orchestrator import validate_for_fulfillment
    r = validate_for_fulfillment({"product_type": "digital"}, None, "", "")
    assert r["ok"]


def test_auto_pipeline_holds_and_does_not_route_on_bad_address(tmp_path, monkeypatch):
    """The PRIMARY (auto-approve) path must validate before routing: an
    incomplete address holds the order and never calls the vendor."""
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    _seed(tmp_path, monkeypatch)
    import quoteforge.automation.pipeline_orchestrator as po
    routed = []
    with patch("quoteforge.fulfillment.router.route_order",
               side_effect=lambda *a, **k: routed.append(a) or
               {"status": "submitted", "id": "X", "vendor": "gelato"}):
        out = po.run_full_pipeline(
            {"order_id": "GATE-1", "recipient_name": "Ann",
             "occasion": "Birthday"},
            skip_proof=True, gelato_product_uid="uid",
            recipient_address={"name": "Ann", "country": "US"})  # incomplete
    assert not routed, "vendor was called despite an invalid address"
    assert out.get("status") == "hold_validation"


def test_auto_pipeline_routes_on_complete_order(tmp_path, monkeypatch):
    """A complete order on the auto path passes the gate and routes once."""
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    _seed(tmp_path, monkeypatch)
    import quoteforge.automation.pipeline_orchestrator as po
    routed = []
    with patch("quoteforge.fulfillment.router.route_order",
               side_effect=lambda *a, **k: routed.append(1) or
               {"status": "submitted", "id": "X", "vendor": "gelato"}):
        out = po.run_full_pipeline(
            {"order_id": "GATE-2", "recipient_name": "Ann",
             "occasion": "Birthday"},
            skip_proof=True, gelato_product_uid="uid",
            recipient_address=GOOD_ADDR)
    assert routed, "complete order was not routed"
    assert out.get("status") != "hold_validation"
