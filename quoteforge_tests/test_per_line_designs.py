"""Per-line design persistence: a multi-item basket must save EVERY item's full
design (apparel front+back, calendar months, each item's wording) - not just the
last-open editor design. REGRESSION for the order-flow audit's design-loss gap.
"""
import json


def _design_json():
    return json.dumps({
        "contact": {"name": "Buyer", "addr": "1 St", "city": "X",
                    "zip": "90001", "country": "US"},
        "cart": {"subtotal": 50.0, "items": 2, "lines": [
            {"title": "Poster", "fmt": "Framed", "size": "16x20", "unit": 25, "qty": 1,
             "design": {"wording": "Happy Birthday Alice", "size": "16x20",
                        "photo": {"has": True}}},
            {"title": "Shirt", "fmt": "Tee", "size": "M", "unit": 25, "qty": 1,
             "placement": "front", "sides": {"front": True, "back": True},
             "design": {"wording": "Team Bob",
                        "sides": {"front": {"quote": "Front text"},
                                  "back": {"quote": "Back text"}}}},
        ]}})


def test_every_line_design_is_saved(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.design_confirm import confirm_design
    res = confirm_design("buyer@x.com", summary="2 items",
                         design_json=_design_json(), design_id="cart-1")
    assert res["ok"] and res["order_id"]
    # the saved design carries BOTH line designs - not just the last
    d = db.get_design_for_order(res["order_id"])
    saved = json.loads(d["design_json"])
    lines = saved["cart"]["lines"]
    assert len(lines) == 2
    assert lines[0]["design"]["wording"] == "Happy Birthday Alice"
    # apparel BACK side preserved (the headline dropped data)
    assert lines[1]["design"]["sides"]["back"]["quote"] == "Back text"


def test_order_line_items_stay_thin(tmp_path, monkeypatch):
    # The order's line_items keep display/financial fields only; the heavy per-line
    # design lives in the saved design, not duplicated onto the order row.
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.design_confirm import _cart_money
    money = _cart_money(_design_json())
    li = json.loads(money["line_items"])
    assert len(li) == 2 and all("design" not in line for line in li)
    assert li[0]["title"] == "Poster" and li[1]["size"] == "M"
