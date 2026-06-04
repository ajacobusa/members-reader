"""Tests that the webhook captures the real Etsy sale price onto the order."""
from unittest.mock import patch

from quoteforge.automation.webhook_server import _parse_money, process_webhook_payload


def test_parse_money_variants():
    assert _parse_money("29.99") == 29.99
    assert _parse_money("$34.50") == 34.50
    assert _parse_money("1,299.00") == 1299.00
    assert _parse_money(45) == 45.0
    assert _parse_money(None) is None
    assert _parse_money("") is None
    assert _parse_money("abc") is None


def test_webhook_stores_sale_price(tmp_path):
    import quoteforge.db.database as db
    payload = {
        "recipient_name": "Emma", "occasion": "Graduation",
        "order_id": "PRICE-1", "customer_name": "Jen",
        "total": "$34.99",  # Etsy order total mapped by Make.com
    }
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.webhook_server.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        process_webhook_payload(payload)
        order = db.get_order_by_etsy_id("PRICE-1")
    assert order is not None
    assert order["sale_price"] == 34.99   # real price captured


def test_webhook_without_price_leaves_null(tmp_path):
    import quoteforge.db.database as db
    payload = {"recipient_name": "Sam", "occasion": "Wedding", "order_id": "PRICE-2"}
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.webhook_server.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        process_webhook_payload(payload)
        order = db.get_order_by_etsy_id("PRICE-2")
    # No price in payload → stays null; financials will estimate with the default
    assert order["sale_price"] is None
