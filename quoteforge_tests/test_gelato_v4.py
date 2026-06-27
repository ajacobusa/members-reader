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
