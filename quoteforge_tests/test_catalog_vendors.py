"""Tests for multi-vendor catalog, misc income, and ledger breakdown."""


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_add_product_any_vendor_and_service(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from quoteforge.catalog import registry
    # a non-Gelato product
    r = registry.add_product("Printful Tee", "printful", "PF-TEE", "apparel",
                             "print", cost=12.0, price=29.0)
    assert r["vendor"] == "printful"
    # a service item (no physical fulfillment)
    registry.add_product("Custom Design Service", "service", "", "service",
                         "service", cost=0.0, price=40.0)
    # a digital item
    registry.add_product("Printable PDF", "digital", "", "digital", "digital")
    items = registry.list_products()
    names = {i["name"] for i in items}
    assert {"Printful Tee", "Custom Design Service", "Printable PDF"} <= names
    # built-in Gelato items still present (extensible, not replacing)
    assert any(i["vendor"] == "gelato" for i in items)


def test_unknown_vendor_rejected(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from quoteforge.catalog import registry
    import pytest
    with pytest.raises(ValueError):
        registry.add_product("X", "no_such_vendor")


def test_vendor_summary_lists_vendors(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from quoteforge.catalog.registry import vendor_summary
    txt = vendor_summary()
    for v in ("gelato", "printful", "printify", "digital", "service"):
        assert v in txt


def test_income_and_breakdown_by_channel(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.config.USE_MAKE_COM", False, raising=False)
    monkeypatch.setattr("quoteforge.config.MONTHLY_FIXED_COSTS", 0.0, raising=False)
    # an Etsy order on Gelato
    oid = db.create_order({"order_id": "B1", "product_type": "canvas",
                           "channel": "etsy", "vendor": "gelato"})
    db.update_order(oid, sale_price=100.0, gelato_cost=30.0)
    # affiliate commission income
    db.add_income(12.50, channel="affiliate", source="1-800-Flowers")
    from quoteforge.etsy.ledger import build_breakdown
    bd = build_breakdown("all")
    assert "etsy" in bd["by_channel"] and "affiliate" in bd["by_channel"]
    assert bd["by_channel"]["affiliate"]["net"] == 12.50
    assert bd["by_vendor"]["gelato"]["orders"] == 1
    assert "canvas" in bd["by_product"]


def test_new_commands_registered():
    from quoteforge import admin
    for c in ("vendors", "add-product", "list-products", "add-income",
              "ledger", "ledger-breakdown", "ledger-excel",
              "subscriptions", "subscription-listing", "gift-addon-listing",
              "affiliates"):
        assert c in admin.COMMANDS
