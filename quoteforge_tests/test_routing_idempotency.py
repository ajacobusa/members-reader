"""Regression: supplier routing must be idempotent - a second route_order call
for an already-routed order must NOT create a duplicate supplier order. Guards
the 'duplicate supplier submission' critical risk."""


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


_ADDR = {"name": "A", "address": "1 Main St", "city": "Atlanta", "state": "GA",
         "postCode": "30301", "country": "US"}


def test_first_route_submits_and_stores_supplier_id(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "R1", "etsy_order_id": "E1",
                     "recipient_name": "A", "occasion": "B"})
    db.update_order("R1", vendor="gelato", gelato_product_uid="uid-1")
    from quoteforge.fulfillment.router import route_order
    r = route_order(db.get_order("R1"), recipient=_ADDR, artwork_url="https://x/art.png")
    assert r["status"] == "submitted" and r["id"]
    assert db.get_order("R1")["vendor_order_id"] == r["id"]   # self-stored


def test_duplicate_route_is_blocked(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "R1", "etsy_order_id": "E1",
                     "recipient_name": "A", "occasion": "B"})
    db.update_order("R1", vendor="gelato", gelato_product_uid="uid-1")
    from quoteforge.fulfillment.router import route_order
    first = route_order(db.get_order("R1"), recipient=_ADDR, artwork_url="https://x/art.png")
    second = route_order(db.get_order("R1"), recipient=_ADDR, artwork_url="https://x/art.png")
    assert second["status"] == "duplicate"
    assert second["id"] == first["id"]                        # same supplier order id


def test_replacement_order_not_blocked(tmp_path, monkeypatch):
    """A reprint uses a NEW order id not in the DB - it must still route."""
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "R1-R", "vendor": "gelato",
                     "gelato_product_uid": "uid-1"},
                    recipient=_ADDR, artwork_url="https://x/art.png")
    assert r["status"] == "submitted" and r["id"]
