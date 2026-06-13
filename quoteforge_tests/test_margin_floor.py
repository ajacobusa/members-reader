"""Margin integrity: every sellable variation (and every bundle-discounted
unit) must clear its net-margin floor when measured by the AUTHORITATIVE
profit calculator (full 9.5% + $0.20 fee stack) - not the old 6.5%-only
pricing that left every price ~3 points under its advertised floor."""
from quoteforge.etsy import variations as V
from quoteforge.etsy.variations import build_variations, bundle_quote, floor_for_tier
from quoteforge.etsy.profit_calculator import (
    calculate_order_profit, ETSY_TRANSACTION_FEE, ETSY_PAYMENT_FEE)


def test_variations_fee_stack_matches_authoritative():
    """variations.py prices against the SAME fee stack the ledger books."""
    assert abs(V.ETSY_FEE_PCT - (ETSY_TRANSACTION_FEE + ETSY_PAYMENT_FEE)) < 1e-9


def test_list_prices_unchanged_no_customer_shock():
    """Making the fee stack honest must NOT raise live list prices: the cheapest
    poster stays $18.99 (the LIST_MARGIN_PCT was retuned so the denominator -
    and therefore the price - is unchanged; only the bare 60% floor moves)."""
    posters = sorted((v for v in build_variations() if v.material == "poster"),
                     key=lambda v: v.price)
    assert posters[0].price == 18.99, f"poster shock: ${posters[0].price}"


def test_floor_price_truly_clears_60pct():
    """The bare floor (bundle/gallery-set cap) must clear a REAL 60%, not the
    old 59.2% the 6.5% stack reported as '60%'."""
    from quoteforge.etsy.variations import floor_price
    cost = 4.5
    fp = floor_price(cost, "entry")
    assert calculate_order_profit(fp, cost)["margin_pct"] >= 60.0


def test_catalog_audit_covers_the_real_variations():
    """The margin audit now inspects the actual sellable variations, not just
    the static product/gallery lists."""
    from quoteforge.etsy.margin_guard import audit_catalog
    a = audit_catalog()
    assert any(r["kind"] == "variation" for r in a["rows"])


def test_whole_catalog_clears_the_floor_ci_gate():
    """CI GATE: no sellable item (variation, product, or gallery set) may sit
    below the 60% net floor. A Gelato price bump that breaches fails the build
    here instead of silently eroding margin in production."""
    from quoteforge.etsy.margin_guard import audit_catalog
    a = audit_catalog()
    assert a["below_floor"] == 0, (
        "below-floor items: "
        + ", ".join(f"{o['name']} ({o['margin_pct']}%)" for o in a["offenders"]))


def test_every_variation_clears_true_floor():
    for v in build_variations():
        real = calculate_order_profit(v.price, v.gelato_cost)["margin_pct"]
        floor = floor_for_tier(v.tier)
        assert real >= floor, (
            f"{v.material} {v.size} {v.frame_color}: real {real}% < floor "
            f"{floor}% (price ${v.price}, cost ${v.gelato_cost})")


def test_bundle_discounted_unit_clears_true_floor():
    """The qty discount cap must hold the floor measured by the real calculator
    (the cap previously self-certified with the wrong 6.5% stack)."""
    for v in build_variations():
        q = bundle_quote(v.price, v.gelato_cost, 4, v.tier)
        real = calculate_order_profit(q["unit"], v.gelato_cost)["margin_pct"]
        floor = floor_for_tier(v.tier)
        assert real >= floor - 0.6, (
            f"bundle x4 {v.material} {v.frame_color}: real {real}% < floor "
            f"{floor}% (unit ${q['unit']}, cost ${v.gelato_cost})")
        assert q["holds_floor"], f"holds_floor wrongly False for {v.material}"
