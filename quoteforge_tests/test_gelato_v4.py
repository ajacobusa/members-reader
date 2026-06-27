"""Gelato Create Order uses the CURRENT v4 API (POST /v4/orders) with orderType +
shipmentMethodUid. v3 stays available via GELATO_API_VERSION for back-compat.
All network mocked.
"""


def _send(monkeypatch, version):
    import quoteforge.automation.gelato_api as ga
    import quoteforge.config as cfg
    monkeypatch.setattr(ga, "TEST_MODE", False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "test-key")
    monkeypatch.setattr(cfg, "GELATO_API_VERSION", version)
    monkeypatch.setattr(cfg, "GELATO_SHIPMENT_METHOD", "normal")
    seen = {}

    class _R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "GLT-1"}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, payload=json)
        return _R()
    monkeypatch.setattr(ga.requests, "post", fake_post)
    res = ga.create_gelato_order(
        "O1",
        {"firstName": "Sarah", "addressLine1": "123 Main St", "city": "Augusta",
         "state": "GA", "postCode": "30901", "country": "US", "email": "e@x.com"},
        "http://cdn/a.png", "product-uid-1")
    return res, seen


def test_create_order_is_v4_with_required_fields(monkeypatch):
    res, seen = _send(monkeypatch, "v4")
    assert res["id"] == "GLT-1"
    assert seen["url"].endswith("/v4/orders")                 # current endpoint
    assert seen["headers"]["X-API-KEY"] == "test-key"         # auth header
    p = seen["payload"]
    assert p["orderType"] == "order"                          # v4-required
    assert p["shipmentMethodUid"] == "normal"                 # v4-required
    # the shared contract (matches the seller's starter)
    assert p["orderReferenceId"] == "O1"
    assert p["items"][0]["productUid"] == "product-uid-1"
    assert p["items"][0]["files"][0] == {"type": "default", "url": "http://cdn/a.png"}
    assert p["shippingAddress"]["city"] == "Augusta"


def test_v3_back_compat_has_no_v4_only_fields(monkeypatch):
    _res, seen = _send(monkeypatch, "v3")
    assert seen["url"].endswith("/v3/orders")
    assert "orderType" not in seen["payload"]
    assert "shipmentMethodUid" not in seen["payload"]


def test_gelato_error_body_is_logged(monkeypatch, caplog):
    # #5: a Gelato failure must surface its REASON, not pass silently.
    import quoteforge.automation.gelato_api as ga
    import requests
    import pytest
    monkeypatch.setattr(ga, "TEST_MODE", False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "k")

    class _R:
        status_code = 400
        text = '{"error":"productUid not found"}'

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("400 Bad Request")

        def json(self):
            return {}
    monkeypatch.setattr(ga.requests, "post", lambda *a, **k: _R())
    with caplog.at_level("ERROR"):
        with pytest.raises(requests.exceptions.HTTPError):
            ga.create_gelato_order("O1", {"country": "US"}, "http://x/a.png", "uid")
    assert "productUid not found" in caplog.text and "O1" in caplog.text


def test_non_public_artwork_url_is_held(tmp_path, monkeypatch):
    # #7: a non-public artwork URL (file://) Gelato can't fetch must NOT be submitted.
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "quoteforge")
    monkeypatch.setattr(cfg, "TEST_MODE", False)          # enforce real-submit guards
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    from quoteforge.fulfillment.router import route_order
    res = route_order(
        {"order_id": "O1", "gelato_product_uid": "uid"},
        recipient={"name": "R", "addressLine1": "1 St", "city": "X",
                   "postCode": "30901", "country": "US"},
        artwork_url="file:///local/a.png")
    assert res["status"] == "manual" and "public URL" in res["detail"]
