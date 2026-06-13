"""Shipping variance + profit-by-destination: catch silent margin leakage when
actual shipping exceeds what was modeled/collected, and rank profit by country."""
import json

from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_modeled_shipping_rises_with_zone_and_material():
    from quoteforge.etsy.shipping_audit import modeled_shipping
    us_poster = modeled_shipping("US", "poster")
    intl_poster = modeled_shipping("AU", "poster")
    us_framed = modeled_shipping("US", "framed")
    assert intl_poster > us_poster          # international costs more
    assert us_framed > us_poster            # heavier material costs more


def test_variance_flags_leak_when_actual_exceeds_model():
    from quoteforge.etsy.shipping_audit import shipping_variance
    # actual shipping far above the model for a US poster -> leaking
    v = shipping_variance({"country": "US", "material": "poster",
                           "shipping_cost": 20.0, "shipping_collected": 5.0})
    assert v["leaking"] is True
    assert v["over_model_pct"] > 10


def test_variance_ok_when_actual_within_model():
    from quoteforge.etsy.shipping_audit import shipping_variance
    v = shipping_variance({"country": "US", "material": "poster",
                           "shipping_cost": 5.5, "shipping_collected": 6.0})
    assert v["leaking"] is False


def test_audit_returns_offenders(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    a = db.create_order({"order_id": "S1", "recipient_name": "A",
                         "occasion": "Birthday", "sale_price": 18.99})
    db.update_order(a, country="US", material="poster", gelato_cost=4.5,
                    shipping_cost=18.0, shipping_collected=5.0)
    b = db.create_order({"order_id": "S2", "recipient_name": "B",
                         "occasion": "Wedding", "sale_price": 45.99})
    db.update_order(b, country="US", material="poster", gelato_cost=6.0,
                    shipping_cost=5.5, shipping_collected=6.0)
    from quoteforge.etsy.shipping_audit import audit_shipping
    r = audit_shipping(db.get_all_orders(50))
    assert "S1" in [o["order_id"] for o in r["offenders"]]
    assert "S2" not in [o["order_id"] for o in r["offenders"]]


def test_profit_by_destination_aggregates(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    for i, (c, sale, cost) in enumerate([("US", 18.99, 4.5), ("US", 24.99, 6.0),
                                         ("AU", 18.99, 4.5)]):
        oid = db.create_order({"order_id": f"P{i}", "recipient_name": "X",
                               "occasion": "Birthday", "sale_price": sale})
        db.update_order(oid, country=c, material="poster", gelato_cost=cost,
                        shipping_cost=5.0, shipping_collected=5.0)
    from quoteforge.etsy.shipping_audit import profit_by_destination
    rows = profit_by_destination(db.get_all_orders(50))
    by = {r["country"]: r for r in rows}
    assert by["US"]["orders"] == 2 and by["AU"]["orders"] == 1
    assert by["US"]["revenue"] > by["AU"]["revenue"]


def test_destination_persisted_from_direct_order_contact(tmp_path, monkeypatch):
    """A direct checkout's ship-to country/state is recorded on the order so it
    can be audited (was: never captured)."""
    db = _seed(tmp_path, monkeypatch)
    design = json.dumps({"contact": {"name": "Ann", "addr": "1 St",
                                     "city": "Atlanta", "state": "GA",
                                     "zip": "30301", "country": "US",
                                     "email": "a@b.com"}})
    from quoteforge.automation.design_confirm import confirm_design
    r = confirm_design("a@b.com", summary="x", design_json=design,
                       design_id="cart-1", send=False)
    o = db.get_order(r["order_id"])
    assert o["country"] == "US" and o["state"] == "GA"
