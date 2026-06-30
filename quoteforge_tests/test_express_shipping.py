"""Express delivery upgrade - a paid, per-order Gelato shipment method, OFF by
default. When enabled, the buyer's express choice rides on the order and the
router ships it to Gelato with the express method instead of the default."""


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"id": "G1", "gelato_order_id": "G1"}


def test_express_is_off_by_default():
    import quoteforge.config as cfg
    # Safe: until the owner enables it, the shop never offers or ships express.
    assert cfg.EXPRESS_SHIPPING_ENABLED is False
    assert cfg.EXPRESS_SHIPPING_UPCHARGE == 9.95          # pre-set price
    assert cfg.EXPRESS_SHIPMENT_METHOD == "express"       # default Gelato express UID


def test_express_shipment_method_gated_on_config(monkeypatch):
    import quoteforge.config as cfg
    from quoteforge.automation.webhook_server import _express_shipment_method
    # Disabled -> NEVER express, no matter what the line says.
    monkeypatch.setattr(cfg, "EXPRESS_SHIPPING_ENABLED", False)
    assert _express_shipment_method({"express_shipping": True}) == ""
    assert _express_shipment_method({"shipment_method": "express"}) == ""
    # Enabled -> express only when the buyer chose it.
    monkeypatch.setattr(cfg, "EXPRESS_SHIPPING_ENABLED", True)
    monkeypatch.setattr(cfg, "EXPRESS_SHIPMENT_METHOD", "express")
    assert _express_shipment_method({"express_shipping": True}) == "express"
    assert _express_shipment_method({"shipment_method": "express"}) == "express"
    assert _express_shipment_method({}) == ""             # not chosen -> default


def test_order_persists_shipment_method(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.create_order({"order_id": "E1", "recipient_name": "R", "occasion": "B",
                     "shipment_method": "express"})
    assert db.get_order("E1")["shipment_method"] == "express"


def test_gelato_payload_uses_per_order_shipment_method(monkeypatch):
    # REGRESSION: the order's chosen method must reach Gelato (else express never ships).
    import quoteforge.config as cfg
    import quoteforge.automation.gelato_api as ga
    import requests
    monkeypatch.setattr(ga, "TEST_MODE", False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "k")
    monkeypatch.setattr(cfg, "GELATO_API_VERSION", "v4")
    sent = {}

    def _post(url, headers=None, json=None, timeout=None):
        sent.update(json or {})
        return _Resp()
    monkeypatch.setattr(requests, "post", _post)
    rec = {"name": "R", "address": "1 St", "city": "ATL", "state": "GA",
           "postCode": "30301", "country": "US"}
    ga.create_gelato_order("E1", rec, "http://x/a.png", "uid", 1,
                           shipment_method="express")
    assert sent.get("shipmentMethodUid") == "express"     # express wins
    sent.clear()
    ga.create_gelato_order("E2", rec, "http://x/a.png", "uid", 1)
    assert sent.get("shipmentMethodUid") in ("normal", cfg.GELATO_SHIPMENT_METHOD)
