"""Packaging + reprint reserve + marketing are real OPERATING costs that come
out of the 60% contribution margin. They're surfaced honestly in reporting
(operating_order_profit / TCO) without changing the contribution floor or any
list price."""


def test_contribution_profit_excludes_operating_costs():
    """calculate_order_profit is contribution-only (what prices/floor use)."""
    from quoteforge.etsy.profit_calculator import calculate_order_profit
    p = calculate_order_profit(36.99, 12.0)
    assert p["packaging_cost"] == 0.0 and p["reprint_reserve"] == 0.0
    # net = sale - cost - fees, nothing else
    assert abs(p["net_profit"] - (36.99 - 12.0 - p["total_fees"])) < 0.01


def test_operating_profit_subtracts_packaging_and_reserve():
    """operating_order_profit is the fully-loaded 'what you actually keep'."""
    from quoteforge.etsy.profit_calculator import (calculate_order_profit,
                                                   operating_order_profit)
    from quoteforge.config import PACKAGING_COST_USD, REPRINT_RESERVE_PCT
    contrib = calculate_order_profit(36.99, 12.0)
    op = operating_order_profit(36.99, 12.0)
    assert op["packaging_cost"] == PACKAGING_COST_USD
    assert op["reprint_reserve"] == round(12.0 * REPRINT_RESERVE_PCT / 100.0, 2)
    assert op["net_profit"] < contrib["net_profit"]
    diff = round(contrib["net_profit"] - op["net_profit"], 2)
    assert diff == round(op["packaging_cost"] + op["reprint_reserve"] + op["cac"], 2)


def test_operating_costs_are_physical_only():
    """Digital/zero-cost items carry no packaging or reprint reserve."""
    from quoteforge.etsy.profit_calculator import operating_order_profit
    o = operating_order_profit(20.0, 0.0)
    assert o["packaging_cost"] == 0.0 and o["reprint_reserve"] == 0.0


def test_tco_variable_costs_include_operating_costs():
    """The TCO's variable monthly costs are fully loaded (packaging + reserve)."""
    from quoteforge.etsy.tco import variable_monthly_costs
    v = variable_monthly_costs(60, 36.99, 12.0)
    assert v["packaging"] > 0 and v["reprint_reserve"] > 0
    assert v["total"] > v["gelato_print"] + v["etsy_fees"]


def test_contribution_floor_unchanged_no_item_below():
    """The contribution floor (and every price) is untouched: no catalog item
    falls below 60% after adding the operating-cost reporting."""
    from quoteforge.etsy.margin_guard import audit_catalog
    assert audit_catalog()["below_floor"] == 0
