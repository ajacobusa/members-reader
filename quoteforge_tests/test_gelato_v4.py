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


def test_extract_gelato_cost_handles_common_shapes():
    # #8: parse the ACTUAL charged cost from a Gelato order response.
    from quoteforge.automation.gelato_api import _extract_gelato_cost
    assert _extract_gelato_cost({"totalInclVat": "19.25"}) == 19.25
    assert _extract_gelato_cost(
        {"receipts": [{"totalInclVat": 10.0}, {"totalInclVat": 9.25}]}) == 19.25
    assert _extract_gelato_cost(
        {"receipts": [{"productsPriceInclVat": 13.0,
                       "shippingPriceInclVat": 6.25}]}) == 19.25
    assert _extract_gelato_cost({}) is None        # not priced yet -> estimate stands


def test_actual_gelato_cost_overwrites_estimate(tmp_path, monkeypatch):
    # #8: when Gelato has priced the order, store the REAL cost (COGS) over the catalog
    # estimate, so financials + the Wave books use actuals.
    import sqlite3
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,gelato_cost) "
                 "VALUES (?,?,?,?)", ("O1", "R", "B", 13.0))     # estimate
    conn.commit()
    conn.close()
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(ga, "get_gelato_order_status",
                        lambda gid: {"tracking_number": "", "cost": 19.25})
    ga.check_and_update_tracking("O1", "GLT-1")
    assert db.get_order("O1")["gelato_cost"] == 19.25            # actual, not 13.0


def test_extract_gelato_shipping():
    from quoteforge.automation.gelato_api import _extract_gelato_shipping
    assert _extract_gelato_shipping({"receipts": [{"shippingPriceInclVat": 6.25}]}) == 6.25
    assert _extract_gelato_shipping({"shippingPriceInclVat": 5.0}) == 5.0
    assert _extract_gelato_shipping({}) is None


def test_actual_cost_splits_product_and_shipping(tmp_path, monkeypatch):
    # Shipping is broken out: gelato_cost = PRODUCT (total - shipping), shipping_cost =
    # shipping. COGS (gelato_cost + shipping_cost) still totals correctly (no double-
    # count), and the shipping-variance audit gets a real Gelato shipping figure.
    import sqlite3
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,gelato_cost) "
                 "VALUES (?,?,?,?)", ("O1", "R", "B", 13.0))
    conn.commit()
    conn.close()
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(ga, "get_gelato_order_status",
                        lambda gid: {"tracking_number": "", "cost": 19.25,
                                     "shipping_cost": 6.25})
    ga.check_and_update_tracking("O1", "GLT-1")
    o = db.get_order("O1")
    assert o["gelato_cost"] == 13.0 and o["shipping_cost"] == 6.25     # product + ship


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
