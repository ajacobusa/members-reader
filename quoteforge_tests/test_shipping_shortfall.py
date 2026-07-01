"""Order-time shipping-shortfall guard: when shipping is charged separately, an order
that collected less shipping than our cost is flagged immediately (a mis-set Etsy
shipping profile can't silently lose money on every order)."""
from quoteforge.automation.order_monitor import audit_order

_BASE = {"order_id": "O", "status": "shipped", "proof_approved": 1,
         "vendor_order_id": "V", "product_type": "apparel", "quantity": 1}


def test_undercollected_shipping_is_flagged(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "FREE_SHIPPING_BAKED", False)
    r = audit_order({**_BASE, "shipping_collected": 0.0})          # Etsy collected nothing
    assert any("shipping collected" in x and "14.70" in x for x in r["review"])


def test_adequate_shipping_not_flagged(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "FREE_SHIPPING_BAKED", False)
    r = audit_order({**_BASE, "shipping_collected": 15.00})        # covers the $14.70 cost
    assert not any("shipping collected" in x for x in r["review"])


def test_skipped_when_shipping_is_baked(monkeypatch):
    # REGRESSION: if shipping is IN the price, a $0 collected is correct - don't flag.
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "FREE_SHIPPING_BAKED", True)
    r = audit_order({**_BASE, "shipping_collected": 0.0})
    assert not any("shipping collected" in x for x in r["review"])
