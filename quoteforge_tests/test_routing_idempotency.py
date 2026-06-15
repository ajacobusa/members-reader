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


def test_dedup_lookup_failure_fails_safe(tmp_path, monkeypatch):
    """REGRESSION: if the dedup lookup raises, route_order must NOT proceed
    (routing anyway could double-submit). It returns an error instead."""
    _seed(tmp_path, monkeypatch)
    import quoteforge.db.database as database

    def boom(_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(database, "get_order", boom)
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "R9", "vendor": "gelato",
                     "gelato_product_uid": "uid-1"},
                    recipient=_ADDR, artwork_url="https://x/art.png")
    assert r["status"] == "error"
    assert "duplicate" in r["detail"].lower()


def test_customer_proof_resume_idempotent_and_stores_vendor_id(tmp_path, monkeypatch):
    """REGRESSION: the manual customer-proof path must route via route_order -
    store vendor_order_id on first approval and NOT double-submit on a re-run
    (previously it called the supplier API directly: no guard, no vendor_id)."""
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "CP1", "recipient_name": "A", "occasion": "B",
                     "vendor": "gelato"})
    db.update_order("CP1", artwork_url="https://x/art.png")  # set after create
    from quoteforge.automation import pipeline_orchestrator as po
    monkeypatch.setattr(po, "validate_for_fulfillment",
                        lambda *a, **k: {"ok": True, "issues": []})
    calls = []
    import quoteforge.automation.gelato_api as gapi
    monkeypatch.setattr(gapi, "create_gelato_order",
                        lambda **kw: (calls.append(kw), {"id": "GELX"})[1])
    po.resume_after_proof_approval("CP1", gelato_product_uid="uid-1",
                                   recipient_address=_ADDR)
    o = db.get_order("CP1")
    assert o["vendor_order_id"] == "GELX"      # vendor id now persisted (the gap)
    assert o["status"] == "in_production"
    po.resume_after_proof_approval("CP1", gelato_product_uid="uid-1",
                                   recipient_address=_ADDR)
    assert len(calls) == 1                      # idempotent - no duplicate submit
