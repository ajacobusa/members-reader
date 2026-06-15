"""Order-time margin-floor regression tests.

The catalog margin audit only covers the static price book. A REAL order can
still land below the floor (custom/discounted price, live cost spike, heavy
upcharge). The compliance monitor must surface such an order for review."""


def test_below_floor_order_flagged_for_review():
    from quoteforge.automation.order_monitor import audit_order
    # Sale $20 against a $15 print cost -> well below the 60% floor.
    a = audit_order({"order_id": "MF1", "status": "received",
                     "sale_price": 20.0, "gelato_cost": 15.0})
    assert any("floor" in r.lower() for r in a["review"])


def test_healthy_margin_order_not_flagged():
    from quoteforge.automation.order_monitor import audit_order
    # Sale $60 against a $9 print cost -> comfortably above the floor.
    a = audit_order({"order_id": "MF2", "status": "received",
                     "sale_price": 60.0, "gelato_cost": 9.0})
    assert not any("floor" in r.lower() for r in a["review"])


def test_free_order_with_real_cost_is_flagged():
    # REGRESSION: a $0 sale (giveaway / 100%-off coupon) against a real print
    # cost is the worst margin case and must NOT be skipped by a truthiness test.
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "MF4", "status": "received",
                     "sale_price": 0.0, "gelato_cost": 12.0})
    assert any("floor" in r.lower() for r in a["review"])


def test_placeholder_zero_cost_order_is_not_flagged():
    # A pre-pricing placeholder (no real cost) has no economics to audit.
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "MF5", "status": "received",
                     "sale_price": 0.0, "gelato_cost": 0.0})
    assert not any("floor" in r.lower() for r in a["review"])


def test_order_without_cost_is_not_margin_checked():
    from quoteforge.automation.order_monitor import audit_order
    # No recorded cost yet -> nothing to check, no false flag.
    a = audit_order({"order_id": "MF3", "status": "received",
                     "sale_price": 20.0})
    assert not any("floor" in r.lower() for r in a["review"])
