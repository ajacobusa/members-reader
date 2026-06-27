"""Multi-item Etsy orders: a receipt with several transactions must become ONE order
LINE PER transaction (each fulfilled), not a single flattened order at the full grand
total. REGRESSION for the order-flow audit's top live bug.
"""


def _multi_receipt():
    return {
        "receipt_id": 555, "name": "Buyer",
        "grandtotal": {"amount": 6000, "divisor": 100},          # 60.00
        "total_shipping_cost": {"amount": 500, "divisor": 100},
        "total_tax_cost": {"amount": 320, "divisor": 100},
        "country_iso": "US", "state": "CA",
        "transactions": [
            {"title": "Poster", "quantity": 1,
             "price": {"amount": 2000, "divisor": 100},          # 20.00
             "variations": [
                 {"formatted_name": "Recipient Name", "formatted_value": "Alice"},
                 {"formatted_name": "Occasion", "formatted_value": "Birthday"},
                 {"formatted_name": "Size", "formatted_value": "16x20"}]},
            {"title": "Mug", "quantity": 2,
             "price": {"amount": 1500, "divisor": 100},          # 15.00 x2 = 30.00
             "variations": [
                 {"formatted_name": "Recipient Name", "formatted_value": "Bob"},
                 {"formatted_name": "Occasion", "formatted_value": "Wedding"},
                 {"formatted_name": "Size", "formatted_value": "11oz"}]},
        ],
    }


def test_multi_transaction_receipt_becomes_items():
    from quoteforge.automation.etsy_api import receipt_to_order_payload
    p = receipt_to_order_payload(_multi_receipt())
    assert "items" in p and len(p["items"]) == 2
    # order-level grand total + tax kept for reconciliation
    assert p["sale_price"] == 60.00 and p["tax_collected"] == 3.20
    a, b = p["items"]
    # each line keeps its OWN size, occasion, recipient and PRE-TAX line price
    assert a["product_size"] == "16x20" and a["occasion"] == "Birthday"
    assert a["recipient_name"] == "Alice" and a["sale_price"] == 20.00
    assert b["product_size"] == "11oz" and b["recipient_name"] == "Bob"
    assert b["sale_price"] == 30.00                              # 15.00 x 2
    # tax/shipping never duplicated onto the lines
    assert "tax_collected" not in a and "shipping_collected" not in a


def test_single_transaction_receipt_stays_flat():
    # Back-compat: a single-item receipt is unchanged (no items[]).
    from quoteforge.automation.etsy_api import receipt_to_order_payload
    receipt = {"receipt_id": 1, "name": "Buyer",
               "grandtotal": {"amount": 2000, "divisor": 100},
               "transactions": [{"variations": [
                   {"formatted_name": "Recipient Name", "formatted_value": "Emma"},
                   {"formatted_name": "Occasion", "formatted_value": "Graduation"}]}]}
    p = receipt_to_order_payload(receipt)
    assert "items" not in p
    assert p["recipient_name"] == "Emma" and p["occasion"] == "Graduation"


def test_multi_item_order_creates_a_line_per_item(tmp_path, monkeypatch):
    # End-to-end: the multi-item payload creates TWO orders, one per transaction.
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.etsy_api import receipt_to_order_payload
    from quoteforge.automation.webhook_server import process_webhook_payload
    payload = receipt_to_order_payload(_multi_receipt())
    res = process_webhook_payload(payload)
    assert res.get("items") == 2 and res.get("processed") == 2
    orders = db.get_all_orders(limit=100)
    assert len(orders) == 2
    sizes = sorted((o.get("size") or o.get("product_size") or "") for o in orders)
    # both products' sizes are present - neither item was dropped
    assert any("16x20" in s for s in sizes) and any("11oz" in s for s in sizes)
