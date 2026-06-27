"""End-to-end UAT: take a real order ALL the way - intake -> quote -> artwork ->
route -> ship -> DELIVERED, with the ACTUAL Gelato cost captured and the books
reconciled. The existing pipeline E2E stops at 'shipped'; this closes the loop
through delivery, cost capture (product vs shipping split), and financials.
All external calls are TEST_MODE / mocked.
"""
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def iso(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "uat.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db
        init_db()
        yield tmp_path


_ORDER = {
    "order_id": "UAT-001", "etsy_order_id": "ETSY-UAT-1",
    "customer_name": "Jennifer Smith", "customer_email": "jen@example.com",
    "recipient_name": "Emma", "sender_name": "Mom", "relationship": "To My Daughter",
    "occasion": "Graduation", "scenery": "Mountains",
    "tone": "Inspirational & Motivational", "memory": "She never gave up.",
    "output_style": "Personal Letter",
}


def _run_pipeline():
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    run_full_pipeline(
        _ORDER, skip_proof=True, gelato_product_uid="poster_18x24_uid",
        recipient_address={"name": "Emma", "address": "1 Main St", "city": "Atlanta",
                           "state": "GA", "postCode": "30301", "country": "US",
                           "email": "e@x.com"})


def _deliver(monkeypatch, total=22.50, ship=6.50):
    """Drive the tracking poll with a mocked Gelato 'delivered' + priced response."""
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(ga, "get_gelato_order_status",
                        lambda g: {"tracking_number": "TN-UAT-9", "status": "delivered",
                                   "cost": total, "shipping_cost": ship,
                                   "carrier": "UPS", "estimated_delivery": ""})
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    return sync_tracking()


def test_full_lifecycle_order_to_delivered_with_actual_cost(iso, monkeypatch):
    _run_pipeline()
    from quoteforge.db.database import get_order, update_order
    o = get_order("UAT-001")
    assert o["status"] == "shipped"                       # pipeline reached shipped
    gid = o.get("vendor_order_id") or o.get("gelato_order_id")
    assert gid                                            # a supplier order id exists
    update_order("UAT-001", gelato_cost=10.0, sale_price=39.0)   # estimate, to be replaced

    _deliver(monkeypatch, total=22.50, ship=6.50)

    o2 = get_order("UAT-001")
    assert o2["status"] == "delivered"                   # closed the loop
    assert o2["delivery_confirmed"] == 1                 # vendor-confirmed, not assumed
    assert o2["tracking_number"] == "TN-UAT-9"
    # ACTUAL cost captured + split: product = total - shipping (no double-count)
    assert o2["gelato_cost"] == 16.0
    assert o2["shipping_cost"] == 6.50


def test_books_reconcile_after_delivery(iso, monkeypatch):
    _run_pipeline()
    from quoteforge.db.database import update_order, get_order
    update_order("UAT-001", gelato_cost=10.0, sale_price=39.0,
                 shipping_collected=5.0, tax_collected=2.5)
    _deliver(monkeypatch, total=22.50, ship=6.50)

    from quoteforge.etsy.financials import order_financials
    f = order_financials(get_order("UAT-001"))
    # product revenue is tax-exclusive; COGS = gelato_cost(product) + shipping_cost
    assert f["product_revenue"] == 36.5                  # 39.0 - 2.5 tax
    assert f["gelato_cost"] == 16.0 and f["gelato_shipping"] == 6.5
    assert f["net_profit"] < f["product_revenue"]        # costs actually deducted
    assert f["sales_tax_collected"] == 2.5               # pass-through tracked


def test_delivered_order_is_terminal_for_the_tracker(iso, monkeypatch):
    # REGRESSION: once delivered, a re-poll must not resurrect or re-ship it.
    _run_pipeline()
    _deliver(monkeypatch)
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    r = sync_tracking()                                  # second poll
    from quoteforge.db.database import get_order
    assert get_order("UAT-001")["status"] == "delivered"
    assert "UAT-001" not in r["newly_shipped"]
