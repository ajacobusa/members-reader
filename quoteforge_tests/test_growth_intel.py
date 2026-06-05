"""Tests for the growth-intelligence agent."""
from unittest.mock import patch

from quoteforge.etsy.growth_intel import (
    segment_performance, growth_actions, format_growth_text,
)
from quoteforge import admin


def _seed(db, n_daughter=12, n_son=2):
    for i in range(n_daughter):
        oid = f"D{i}"
        db.create_order({"order_id": oid, "recipient_name": f"d{i}",
                         "relationship": "Daughter", "occasion": "Graduation",
                         "sale_price": 49.0, "gelato_cost": 11.0})
        db.update_order(oid, status="shipped")
    for i in range(n_son):
        oid = f"S{i}"
        db.create_order({"order_id": oid, "recipient_name": f"s{i}",
                         "relationship": "Son", "occasion": "Birthday",
                         "sale_price": 30.0, "gelato_cost": 11.0})
        db.update_order(oid, status="shipped")


def test_segment_performance_aggregates():
    orders = [
        {"relationship": "Daughter", "occasion": "Graduation",
         "sale_price": 49.0, "gelato_cost": 11.0, "status": "shipped"},
        {"relationship": "Daughter", "occasion": "Graduation",
         "sale_price": 49.0, "gelato_cost": 11.0, "status": "shipped"},
    ]
    perf = segment_performance(orders)
    assert perf["relationship"]["Daughter"]["orders"] == 2
    assert perf["relationship"]["Daughter"]["revenue"] == 98.0
    assert perf["relationship"]["Daughter"]["profit"] > 0


def test_launch_phase_when_few_orders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _seed(db, n_daughter=3, n_son=0)
        g = growth_actions()
    assert g["phase"] == "launch"
    assert g["next_listings"]


def test_scaling_phase_identifies_winner(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _seed(db, n_daughter=12, n_son=2)
        g = growth_actions()
    assert g["phase"] == "scaling"
    winners = [w["segment"] for w in g["scale"]]
    assert "Daughter" in winners      # the clear winner by profit


def test_growth_text_renders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _seed(db, n_daughter=12, n_son=2)
        text = format_growth_text(growth_actions())
    assert "GROWTH INTELLIGENCE" in text and "SCALE THESE WINNERS" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_growth(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["growth"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GROWTH INTELLIGENCE" in out
