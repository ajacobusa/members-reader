"""Order money integrity: the customer's basket total, item count, and line
items must be RECORDED on the order so the ledger/reconciliation see real
revenue (was sale_price=None -> every direct sale booked $0)."""
import json

from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _design(subtotal, items, lines):
    return json.dumps({
        "contact": {"name": "Ann", "addr": "1 St", "city": "Atlanta",
                    "state": "GA", "zip": "30301", "country": "US",
                    "email": "ann@b.com", "phone": "555"},
        "cart": {"subtotal": subtotal, "items": items, "lines": lines},
    })


def test_confirm_records_sale_price_item_count_and_lines(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    lines = [{"fmt": "Framed - Classic White Wood", "size": "8x10",
              "unit": 58.07, "qty": 3}]
    design = _design(174.21, 3, lines)
    from quoteforge.automation.design_confirm import confirm_design
    r = confirm_design("ann@b.com", summary="x", design_json=design,
                       design_id="cart-abc", send=False)
    o = db.get_order(r["order_id"])
    assert o is not None
    assert abs((o["sale_price"] or 0) - 174.21) < 0.01
    assert o["item_count"] == 3
    saved = json.loads(o["line_items"])
    assert saved[0]["fmt"] == "Framed - Classic White Wood" and saved[0]["qty"] == 3


def test_recorded_sale_reaches_the_ledger_revenue(tmp_path, monkeypatch):
    """A direct sale with a recorded sale_price is counted in revenue (not
    skipped as None)."""
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.automation.design_confirm import confirm_design
    confirm_design("ann@b.com", summary="x",
                   design_json=_design(99.99, 1, [{"fmt": "Poster (unframed)",
                                                   "size": "8x10", "unit": 99.99,
                                                   "qty": 1}]),
                   design_id="cart-xyz", send=False)
    o = [r for r in db.get_all_orders(50) if (r.get("sale_price") or 0) > 0]
    assert any(abs(r["sale_price"] - 99.99) < 0.01 for r in o)


def test_distinct_baskets_do_not_collapse(tmp_path, monkeypatch):
    """Two checkouts from the same email with distinct cart ids create TWO
    orders (was: same WEB- id from design_id='default' overwrote the first)."""
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.automation.design_confirm import confirm_design
    r1 = confirm_design("ann@b.com", summary="a",
                        design_json=_design(50.0, 1, []), design_id="cart-1",
                        send=False)
    r2 = confirm_design("ann@b.com", summary="b",
                        design_json=_design(75.0, 1, []), design_id="cart-2",
                        send=False)
    assert r1["order_id"] != r2["order_id"]
    assert db.get_order(r1["order_id"]) and db.get_order(r2["order_id"])
