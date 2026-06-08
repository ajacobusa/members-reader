"""Profit Optimization Engine + Abandoned Customization Recovery (real data)."""
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


# ── profit optimizer ──

def test_profit_empty(fresh_db):
    from quoteforge.analytics.profit_optimizer import optimize, format_profit_text
    o = optimize()
    assert o["sales"] == 0 and o["total_net_profit"] == 0.0
    assert "No confirmed sales yet" in format_profit_text()


def test_profit_by_dimension(fresh_db):
    db = fresh_db
    db.create_order({"order_id": "P1", "sale_price": 100.0, "gelato_cost": 20.0,
                     "material": "Framed", "size": "18x24", "listing": "Vows"})
    db.create_order({"order_id": "P2", "sale_price": 40.0, "gelato_cost": 10.0,
                     "material": "Poster", "size": "12x16", "listing": "Vows"})
    from quoteforge.analytics.profit_optimizer import profit_by, optimize
    by_mat = profit_by("material")
    assert by_mat[0]["key"] == "Framed"  # most net profit first
    assert by_mat[0]["net_profit"] > by_mat[1]["net_profit"]
    o = optimize()
    assert o["sales"] == 2 and o["total_revenue"] == 140.0
    assert o["best_by_dimension"]["listing"]["key"] == "Vows"
    assert o["insights"]  # material has 2 distinct keys -> insight generated


def test_profit_unknown_dimension(fresh_db):
    from quoteforge.analytics.profit_optimizer import profit_by
    with pytest.raises(ValueError):
        profit_by("nope")


def test_profit_ignores_unpriced_orders(fresh_db):
    db = fresh_db
    db.create_order({"order_id": "U1", "material": "Framed"})  # no sale_price
    from quoteforge.analytics.profit_optimizer import optimize
    assert optimize()["sales"] == 0


# ── customization recovery ──

def test_save_and_recover(fresh_db):
    db = fresh_db
    db.save_customization("Buyer@X.com", listing="Vows", material="Framed",
                          wording="Always & forever", has_photo=True)
    open_items = db.get_open_customizations()
    assert len(open_items) == 1 and open_items[0]["email"] == "buyer@x.com"
    from quoteforge.automation.customization_recovery import run_recovery
    r = run_recovery(older_than_minutes=0, send=False)
    assert r["candidates"] == 1 and "still waiting" in r["results"][0]["message"].lower() \
        or r["candidates"] == 1


def test_converted_not_recovered(fresh_db):
    db = fresh_db
    db.save_customization("a@b.com", listing="Vows", wording="hi")
    db.mark_customization("a@b.com", "Vows", "converted")
    assert db.get_open_customizations() == []


def test_save_customization_requires_email(fresh_db):
    assert fresh_db.save_customization("noemail", listing="x") == 0


def test_customization_endpoint(fresh_db, monkeypatch):
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    monkeypatch.setattr("quoteforge.db.database.save_customization", lambda **k: 1)
    c = app.test_client()
    ok = c.post("/customization", json={"email": "a@b.com", "listing": "Vows",
                                        "material": "Framed", "wording": "hi"})
    assert ok.status_code == 200 and ok.get_json()["status"] == "ok"
    bad = c.post("/customization", json={"listing": "Vows"})
    assert bad.status_code == 400


def test_profit_and_recovery_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "profit" in COMMANDS and "recover-customizations" in COMMANDS
