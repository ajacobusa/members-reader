"""Root-cause fixes from the deep find->verify audit (11 confirmed defects):
- #3/#9 qty>1: gelato_cost stored as a LINE TOTAL so COGS + margin gate are correct
- #4     multi-line storefront basket: gelato_cost = sum(line cost x qty), not first line
- #2     failed reprint claim stays actionable + no false 'on the way' email
- #1     designs link to the MATCHING order line, not by save-recency
- #7     submit_unconfirmed orders surface in the daily attention report
- #5     a future family with no render-size branch fails loudly (no wrong-size print)
All network mocked / TEST_MODE / tmp.
"""
import json
import sqlite3


def test_qty_gt1_stores_line_total_cogs():
    from quoteforge.automation.webhook_server import _build_order_data
    from quoteforge.etsy.variations import wallart_cost_for
    unit = wallart_cost_for("Poster (unframed print)", "8x10")
    assert unit and unit > 0
    data = _build_order_data(
        {"recipient_name": "R", "occasion": "B",
         "material": "Poster (unframed print)", "product_size": "8x10",
         "quantity": 3}, "")
    assert data["gelato_cost"] == round(unit * 3, 2)        # line total, not per-unit


def test_multiline_basket_sums_cogs(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.design_confirm import _cart_money
    dj = json.dumps({"contact": {"name": "B", "addr": "1 St"},
                     "cart": {"subtotal": 75.0, "items": 3, "lines": [
                         {"title": "Poster", "fmt": "Poster (unframed print)",
                          "size": "8x10", "unit": 25, "qty": 2},
                         {"title": "Poster", "fmt": "Poster (unframed print)",
                          "size": "8x10", "unit": 25, "qty": 1}]}})
    money = _cart_money(dj)
    li = json.loads(money["line_items"])
    expected = sum(float(l["gelato_cost"]) * int(l["qty"])
                   for l in li if l.get("gelato_cost"))
    assert expected > 0
    assert money["gelato_cost"] == round(expected, 2)       # whole-basket COGS, not line 1


def test_failed_reprint_stays_actionable_and_sends_no_false_promise(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    from quoteforge.db import database as db
    db.init_db()
    db.create_order({"order_id": "QF-1", "etsy_order_id": "E1",
                     "customer_email": "buyer@mail.com", "recipient_name": "Ann",
                     "occasion": "Birthday"})
    # delivered + claim filed, but NO ship_to/artwork -> reprint returns needs_input
    db.update_order("QF-1", status="delivered", delivery_confirmed=1,
                    claim_status="filed", gelato_product_uid="uid-1",
                    ship_to="", artwork_url="")
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "approved_reprint", send=True)
    assert r["status"] == "supplier_review"                 # NOT terminal approved_reprint
    assert r["email"] is None                               # no false 'on the way'
    assert db.get_order("QF-1")["claim_status"] == "supplier_review"


def test_designs_link_to_matching_order_not_by_recency(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    # two distinct UNLINKED designs for one buyer; the mug is saved LAST (most recent)
    db.save_design("buyer@x.com", design_json=json.dumps({"fmt": "Poster", "size": "8x10"}),
                   design_id="d-poster")
    db.save_design("buyer@x.com",
                   design_json=json.dumps({"product_type": "mug", "size": "11oz"}),
                   design_id="d-mug")
    # the POSTER order is created first; old recency logic would grab the mug design
    db.create_order({"order_id": "ORD-POSTER", "customer_email": "buyer@x.com",
                     "recipient_name": "R", "occasion": "B",
                     "product_type": "print", "material": "Poster", "size": "8x10"})
    linked = db.get_design_for_order("ORD-POSTER")
    assert linked is not None
    assert json.loads(linked["design_json"]).get("fmt") == "Poster"   # matched, not the mug


def test_submit_unconfirmed_surfaces_in_daily_report(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,status) "
                 "VALUES (?,?,?,?)", ("O1", "R", "B", "submit_unconfirmed"))
    conn.commit()
    conn.close()
    rep = db.daily_order_report()
    assert any(o["order_id"] == "O1" for o in rep["needs_attention"])


def test_unknown_family_does_not_ship_wrong_size(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path)
    from quoteforge.db.database import init_db, get_order
    init_db()
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    order = {"order_id": "PC-1", "recipient_name": "R", "occasion": "B",
             "product_type": "phonecase"}                   # a family with no render branch
    try:
        run_full_pipeline(order, skip_proof=True, gelato_product_uid="real-uid",
                          recipient_address={"name": "R", "addressLine1": "1 St",
                                             "city": "X", "postCode": "30901",
                                             "country": "US"})
    except ValueError:
        pass                                                # failing loudly is acceptable
    o = get_order("PC-1")
    assert o is None or o["status"] != "shipped"            # NEVER auto-shipped wrong-size
