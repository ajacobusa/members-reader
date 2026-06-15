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


def test_order_without_cost_is_not_margin_checked():
    from quoteforge.automation.order_monitor import audit_order
    # No recorded cost yet -> nothing to check, no false flag.
    a = audit_order({"order_id": "MF3", "status": "received",
                     "sale_price": 20.0})
    assert not any("floor" in r.lower() for r in a["review"])
