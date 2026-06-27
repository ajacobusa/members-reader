"""Fixes from the product x scenario re-verification (25 agents):
- HIGH: ordered quantity must reach the Gelato submission (was defaulting to 1)
- MED:  wall-art cost resolves despite the '8x10' vs '8x10 in' size-token mismatch
- MED:  unframed wall-art resolves a Gelato productUid (was held 'manual', empty UID)
All network mocked.
"""
import sqlite3


def test_quantity_persisted_on_order(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.create_order({"order_id": "O1", "recipient_name": "R", "occasion": "B",
                     "quantity": 3})
    assert db.get_order("O1")["quantity"] == 3


def test_qty_gt_1_reaches_gelato_submission(tmp_path, monkeypatch):
    # REGRESSION: a qty>1 order must submit quantity>1 (was silently shipping 1 unit).
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "quoteforge")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.create_order({"order_id": "O1", "recipient_name": "R", "occasion": "B",
                     "gelato_product_uid": "uid-1", "quantity": 2})
    import quoteforge.automation.gelato_api as ga
    seen = {}
    monkeypatch.setattr(ga, "create_gelato_order",
                        lambda **k: (seen.update(k), {"id": "GLT-1"})[1])
    from quoteforge.fulfillment.router import route_order
    res = route_order(
        {"order_id": "O1", "gelato_product_uid": "uid-1"},
        recipient={"name": "R", "addressLine1": "1 St", "city": "X",
                   "postCode": "30901", "country": "US"},
        artwork_url="http://x/a.png")
    assert res["status"] == "submitted"
    assert seen["quantity"] == 2


def test_wallart_cost_matches_bare_size_token():
    # REGRESSION: '8x10' (sent) must match the catalog '8x10 in' label -> a real cost.
    from quoteforge.etsy.variations import wallart_cost_for
    cost = wallart_cost_for("Poster (unframed print)", "8x10")
    assert cost is not None and cost > 0


def test_unframed_wallart_resolves_a_uid():
    # REGRESSION: an unframed poster resolves a Gelato productUid (was empty -> manual).
    from quoteforge.etsy.variations import wallart_uid_for
    uid = wallart_uid_for("Poster (unframed print)", "8x10")
    assert uid                                  # a SKU, not empty
    # framed stays None (composite SKU, held for the operator)
    assert wallart_uid_for("Framed - Oak", "8x10") is None


def test_build_order_data_backfills_wallart_uid(monkeypatch):
    from quoteforge.automation.webhook_server import _build_order_data
    data = _build_order_data(
        {"recipient_name": "R", "occasion": "B", "material": "Poster (unframed print)",
         "product_size": "8x10"}, "")
    assert data.get("gelato_product_uid")       # resolved, no longer empty
    assert data.get("gelato_cost")              # cost backfilled too
