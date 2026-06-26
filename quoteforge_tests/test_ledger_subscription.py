"""Tests for the general ledger + subscription product."""
from datetime import date


def _seed_db(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.USE_MAKE_COM", False, raising=False)
    monkeypatch.setattr("quoteforge.config.MONTHLY_FIXED_COSTS", 0.0, raising=False)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_ledger_pnl_math(tmp_path, monkeypatch):
    db = _seed_db(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "L1", "customer_name": "A"})
    # $100 sale, $30 Gelato cost -> fees = 6.5%+3%+0.20 = 9.70 ; net = 60.30.
    # status must be billable (earned) - the ledger excludes non-billable orders.
    db.update_order(oid, sale_price=100.0, gelato_cost=30.0, status="shipped")
    from quoteforge.etsy.ledger import build_ledger
    led = build_ledger("all")
    t = led["totals"]
    assert t["revenue"] == 100.0 and t["cogs"] == 30.0
    assert t["etsy_fees"] == 9.70 and t["net_profit"] == 60.30
    assert t["orders"] == 1


def test_ledger_snapshot_persists(tmp_path, monkeypatch):
    db = _seed_db(tmp_path, monkeypatch)
    from quoteforge.etsy.ledger import snapshot_today
    snapshot_today()
    snaps = db.get_ledger_snapshots()
    assert snaps and snaps[0]["day"] == date.today().isoformat()


def test_ledger_excel_export(tmp_path, monkeypatch):
    _seed_db(tmp_path, monkeypatch)
    from quoteforge.etsy.ledger import export_ledger_excel
    out = export_ledger_excel("all", out_path=tmp_path / "gl.xlsx")
    assert out.exists() and out.stat().st_size > 0


def test_subscription_listing_and_activation(tmp_path, monkeypatch):
    db = _seed_db(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    monkeypatch.setattr("quoteforge.automation.emailer._send_email",
                        lambda *a, **k: None)
    from quoteforge.etsy.subscription_product import (
        build_subscription_listing, start_subscription_from_order, PLANS)
    L = build_subscription_listing()
    assert len(L["plans"]) == len(PLANS) and len(L["tags"]) == 13
    r = start_subscription_from_order(
        {"subscription_plan": "annual", "customer_email": "s@x.com", "customer_name": "Sue"})
    assert r["created"] and r["plan"] == "annual"
    subs = db.get_subscriptions("active")
    assert subs and subs[0]["customer_email"] == "s@x.com"
    # paying subscriber is opted-in
    assert any(s["consent"] == "yes" for s in db.get_subscribers())


def test_non_subscription_order_noop(tmp_path, monkeypatch):
    _seed_db(tmp_path, monkeypatch)
    from quoteforge.etsy.subscription_product import start_subscription_from_order
    assert start_subscription_from_order({"customer_email": "x@y.com"})["created"] is False
