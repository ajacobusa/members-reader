"""Gelato fulfilment mode: exactly ONE source may submit an order to Gelato, or it
double-prints + double-charges. Default is "native" (Gelato pulls from Etsy;
QuoteForge must NOT submit). "quoteforge" mode submits via the API.
"""
import sqlite3


def _order(d, oid="O1"):
    conn = sqlite3.connect(d.DB_PATH)
    cols = {"order_id": oid, "recipient_name": "R", "occasion": "B",
            "status": "received", "product_type": "print", "gelato_product_uid": "uid-1"}
    conn.execute(f"INSERT INTO orders ({','.join(cols)}) "
                 f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    conn.commit()
    conn.close()


def test_native_mode_never_submits_to_gelato(tmp_path, monkeypatch):
    # REGRESSION: with native Etsy<->Gelato fulfilment, QuoteForge must NOT call the
    # Gelato API (that would double-print). route_order short-circuits to 'native'.
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "native")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    _order(db)
    import quoteforge.automation.gelato_api as ga
    called = {"n": 0}
    monkeypatch.setattr(ga, "create_gelato_order",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    from quoteforge.fulfillment.router import route_order
    res = route_order({"order_id": "O1", "gelato_product_uid": "uid-1"},
                      recipient={"name": "R", "addressLine1": "1 St", "city": "X",
                                 "postCode": "90001", "country": "US"},
                      artwork_url="http://x/a.png")
    assert res["status"] == "native" and called["n"] == 0      # never submitted
    o = db.get_order("O1")
    assert o["vendor"] == "gelato-native" and not o.get("vendor_order_id")


def test_quoteforge_mode_submits(tmp_path, monkeypatch):
    # The opt-in QuoteForge->Gelato path DOES submit (for sellers not using the native
    # Etsy integration).
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "quoteforge")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    _order(db)
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(ga, "create_gelato_order",
                        lambda *a, **k: {"id": "GLT-123"})
    from quoteforge.fulfillment.router import route_order
    res = route_order({"order_id": "O1", "gelato_product_uid": "uid-1"},
                      recipient={"name": "R", "addressLine1": "1 St", "city": "X",
                                 "postCode": "90001", "country": "US"},
                      artwork_url="http://x/a.png")
    assert res["status"] == "submitted" and res["id"] == "GLT-123"
