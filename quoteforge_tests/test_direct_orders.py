"""Direct storefront orders: completing an order must alert the OWNER by
email and create a real order record so the fulfillment flow takes over -
a sale is never silent."""
import json
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


_DESIGN = json.dumps({"fmt": "Poster (unframed)", "size": "8x10",
                      "contact": {"name": "Anoop Jacob", "email": "a@b.com",
                                  "addr": "7480 Ashford Dunwoody Rd",
                                  "city": "Atlanta", "state": "GA",
                                  "zip": "30338", "country": "United States",
                                  "phone": "770-9990"}})


def test_confirm_alerts_owner_and_creates_order(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    sent = []
    with patch("quoteforge.automation.emailer._send_email",
               side_effect=lambda subject, body, to="", **k:
               sent.append((subject, to)) or {"status": "sent"}):
        from quoteforge.automation.design_confirm import confirm_design
        r = confirm_design("a@b.com", summary="1x Poster 8x10\nSubtotal: $18.99",
                           design_json=_DESIGN, design_id="D9", send=False)
    assert r["ok"]
    # Owner sale alert fired (to='' -> defaults to the owner/report recipient).
    assert any("storefront order" in s.lower() and not to for s, to in sent)
    # A real order record entered the fulfillment flow.
    oid = r["order_id"]
    assert oid.startswith("WEB-")
    o = db.get_order(oid)
    assert o and o["channel"] == "direct"
    assert o["recipient_name"] == "Anoop Jacob"
    assert o["customer_email"] == "a@b.com"


def test_confirm_is_idempotent_no_duplicate_orders(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    with patch("quoteforge.automation.emailer._send_email",
               return_value={"status": "sent"}):
        from quoteforge.automation.design_confirm import confirm_design
        r1 = confirm_design("a@b.com", summary="s", design_json=_DESIGN,
                            design_id="D9", send=False)
        r2 = confirm_design("a@b.com", summary="s", design_json=_DESIGN,
                            design_id="D9", send=False)
    assert r1["order_id"] == r2["order_id"]
    assert len(db.get_all_orders(50)) == 1


def test_confirm_without_contact_still_works(tmp_path, monkeypatch):
    """Legacy accepts (no shipping details collected) must not break - they
    save the design and alert the owner, just without an order record."""
    _seed(tmp_path, monkeypatch)
    with patch("quoteforge.automation.emailer._send_email",
               return_value={"status": "sent"}):
        from quoteforge.automation.design_confirm import confirm_design
        r = confirm_design("a@b.com", summary="s",
                           design_json=json.dumps({"fmt": "Poster"}),
                           design_id="D1", send=False)
    assert r["ok"] and r["order_id"] == ""
