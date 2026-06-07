"""Tests for per-customer folders + per-vendor catalog pricing."""


def test_customer_folder_and_record(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge import customers
    cid = customers.customer_id("Buyer@X.com")
    assert cid.startswith("C") and cid == customers.customer_id("buyer@x.com")  # stable, case-insensitive
    d = customers.ensure_customer("buyer@x.com", "Bob")
    assert (d / "details.json").exists() and (d / "uploads").is_dir()
    customers.record_order("buyer@x.com", {"order_id": "O1", "occasion": "Birthday",
                                           "recipient_name": "Mom", "sale_price": 36.99})
    import json
    data = json.loads((d / "details.json").read_text(encoding="utf-8"))
    assert data["orders"][0]["order_id"] == "O1" and data["customer_id"] == cid


def test_save_upload(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from PIL import Image
    src = tmp_path / "photo.jpg"; Image.new("RGB", (10, 10)).save(src)
    from quoteforge import customers
    dest = customers.save_upload("buyer@x.com", src)
    assert dest and dest.exists() and dest.parent.name == "uploads"


def test_catalog_item_auto_prices_to_vendor_floor(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.VENDOR_MARGIN_FLOORS_JSON", "", raising=False)
    from quoteforge.db import database as db
    db.init_db()
    from quoteforge.catalog import registry
    from quoteforge.etsy.variations import net_margin_pct
    # a service costing $10 should auto-price to clear the 80% service floor
    r = registry.add_product("Design service", "service", "", "service", "service",
                             cost=10.0)
    assert r["price"] > 0 and net_margin_pct(r["price"], 10.0) >= 80
