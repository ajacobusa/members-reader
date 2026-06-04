"""Tests for the renderer break-even helper (trial decision support)."""
from quoteforge.etsy.profit_calculator import renderer_breakeven, RENDERER_COSTS


def test_local_renderer_is_free():
    r = renderer_breakeven("local", avg_profit_per_order=16.0)
    assert r["monthly_cost"] == 0.0
    assert r["extra_orders_to_break_even"] == 0.0
    assert "Free" in r["verdict"]


def test_bannerbear_breakeven_orders():
    # $49/mo at $16 profit/order → ~3.1 extra orders/month to justify
    r = renderer_breakeven("bannerbear", avg_profit_per_order=16.0)
    assert r["monthly_cost"] == 49.0
    assert r["extra_orders_to_break_even"] == round(49.0 / 16.0, 1)
    assert "extra orders" in r["verdict"]


def test_canva_breakeven_orders():
    r = renderer_breakeven("canva", avg_profit_per_order=16.0)
    assert r["monthly_cost"] == 12.99
    assert r["extra_orders_to_break_even"] == round(12.99 / 16.0, 1)


def test_trial_total_cost_two_months():
    r = renderer_breakeven("bannerbear", avg_profit_per_order=16.0, trial_months=2)
    assert r["total_trial_cost"] == 98.0


def test_zero_profit_safe():
    r = renderer_breakeven("bannerbear", avg_profit_per_order=0.0)
    assert r["extra_orders_to_break_even"] == 0.0


def test_renderer_costs_table():
    assert RENDERER_COSTS["local"] == 0.0
    assert RENDERER_COSTS["bannerbear"] == 49.0
    assert "canva" in RENDERER_COSTS
