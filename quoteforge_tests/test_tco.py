"""Tests for the Total Cost of Ownership calculator."""
from unittest.mock import patch

from quoteforge.etsy.tco import (
    fixed_monthly_costs, variable_monthly_costs, startup_costs,
    estimate_tco, live_tco, format_tco_text,
)
from quoteforge import admin


def test_fixed_costs_include_stack():
    f = fixed_monthly_costs(listings=100, orders_per_month=60)
    items = f["items"]
    assert "Anthropic (Claude Haiku)" in items
    assert "Etsy listing renewals" in items
    # 100 listings * $0.05/mo = $5.00 renewals
    assert items["Etsy listing renewals"] == 5.0
    assert f["total"] > 0


def test_local_renderer_is_free_in_fixed():
    with patch("quoteforge.etsy.tco.RENDERER", "local"):
        f = fixed_monthly_costs(50, 30)
    assert f["items"]["Renderer (local)"] == 0.0


def test_make_com_toggle():
    with patch("quoteforge.etsy.tco.USE_MAKE_COM", True), \
         patch("quoteforge.etsy.tco.MAKE_COM_COST", 9.0):
        on = fixed_monthly_costs(50, 30)["items"]["Make.com automation"]
    with patch("quoteforge.etsy.tco.USE_MAKE_COM", False):
        off = fixed_monthly_costs(50, 30)["items"]["Make.com automation"]
    assert on == 9.0
    assert off == 0.0


def test_variable_scales_with_orders():
    v10 = variable_monthly_costs(10, 29.99, 11.0)
    v100 = variable_monthly_costs(100, 29.99, 11.0)
    assert v100["total"] == round(v10["total"] * 10, 2)
    assert v100["gelato_print"] == 1100.0


def test_startup_costs():
    s = startup_costs(20)
    # 20 listings * $0.20 + $13 sample
    assert s["items"]["Etsy listing fees ($0.20 each)"] == 4.0
    assert s["total"] >= 17.0


def test_estimate_tco_full_breakdown():
    tco = estimate_tco(listings=100, orders_per_month=60,
                       avg_sale_price=29.99, avg_gelato_cost=11.0)
    assert tco["revenue_monthly"] == round(60 * 29.99, 2)
    assert tco["net_profit_monthly"] > 0
    assert tco["net_profit_yearly"] == round(tco["net_profit_monthly"] * 12, 2)
    # Fixed cost should be a small fraction of revenue
    assert tco["fixed_cost_pct_of_revenue"] < 5.0


def test_fixed_cost_is_low_relative_to_revenue():
    tco = estimate_tco(listings=100, orders_per_month=150)
    # At healthy volume, fixed cost is < 1% of revenue
    assert tco["fixed_cost_pct_of_revenue"] < 2.0


def test_live_tco_projection_when_no_orders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        tco = live_tco(listings=50)
    assert "projection" in tco["source"]
    assert tco["fixed_monthly"]["total"] > 0


def test_live_tco_uses_real_orders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "T-1", "recipient_name": "X",
                               "occasion": "Y", "sale_price": 30.0, "gelato_cost": 11.0})
        db.update_order(oid, status="shipped")
        tco = live_tco(listings=50)
    assert "live" in tco["source"]
    assert tco["revenue_monthly"] == 30.0


def test_format_tco_text():
    text = format_tco_text(estimate_tco(100, 60))
    assert "TOTAL COST OF OWNERSHIP" in text
    assert "FIXED MONTHLY" in text
    assert "VARIABLE MONTHLY" in text
    assert "NET PROFIT" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_tco_projection(capsys):
    rc = admin.main(["tco", "100", "60"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "TOTAL COST OF OWNERSHIP" in out
    assert "100 listings, 60 orders/mo" in out


def test_cli_tco_live(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["tco", "50"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "TOTAL COST OF OWNERSHIP" in out
