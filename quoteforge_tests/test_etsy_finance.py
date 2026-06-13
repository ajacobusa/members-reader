"""Read ACTUAL Etsy financials (not estimates): real order total, shipping
collected, sales tax collected, Etsy fees, and net payout - from the Etsy
receipt (already polled) and an Etsy Orders/statement CSV import."""
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _money(amount, divisor=100):
    return {"amount": amount, "divisor": divisor, "currency_code": "USD"}


def test_receipt_captures_real_tax_shipping_destination():
    from quoteforge.automation.etsy_api import receipt_to_order_payload
    receipt = {
        "receipt_id": 12345, "name": "Ann",
        "grandtotal": _money(5221), "total_shipping_cost": _money(599),
        "total_tax_cost": _money(322),
        "country_iso": "US", "state": "GA",
        "transactions": [],
    }
    p = receipt_to_order_payload(receipt)
    assert abs(p["sale_price"] - 52.21) < 0.01
    assert abs(p["shipping_collected"] - 5.99) < 0.01
    assert abs(p["tax_collected"] - 3.22) < 0.01
    assert p["country"] == "US" and p["state"] == "GA"


def test_orders_csv_import_updates_real_figures(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "E1", "etsy_order_id": "3001",
                     "recipient_name": "A", "occasion": "B"})
    csv_text = (
        "Order ID,Order Total,Order Shipping,Order Sales Tax,Ship Country,"
        "Card Processing Fees,Order Net\n"
        "3001,52.21,5.99,3.22,United States,2.45,44.05\n")
    path = tmp_path / "EtsySoldOrders.csv"
    path.write_text(csv_text, encoding="utf-8")
    from quoteforge.etsy.etsy_finance_import import import_orders_csv
    r = import_orders_csv(path)
    assert r["updated"] == 1
    o = db.get_order("E1")
    assert abs(o["sale_price"] - 52.21) < 0.01
    assert abs(o["shipping_collected"] - 5.99) < 0.01
    assert abs(o["tax_collected"] - 3.22) < 0.01
    assert abs(o["etsy_fees_actual"] - 2.45) < 0.01
    assert abs(o["net_payout"] - 44.05) < 0.01


def test_financials_use_actual_when_present():
    from quoteforge.etsy.financials import order_financials
    o = {"order_id": "X", "sale_price": 52.21, "gelato_cost": 6.0,
         "shipping_collected": 5.99, "tax_collected": 3.22,
         "etsy_fees_actual": 2.45, "net_payout": 44.05}
    f = order_financials(o)
    assert abs(f["sales_tax_collected"] - 3.22) < 0.01   # REAL, not estimate
    assert abs(f["etsy_fees"] - 2.45) < 0.01             # REAL fee
    assert abs(f["net_payout"] - 44.05) < 0.01
    assert f["source"] == "etsy_actual"


def test_financials_fall_back_to_estimate():
    from quoteforge.etsy.financials import order_financials
    f = order_financials({"order_id": "Y", "sale_price": 50.0, "gelato_cost": 12.0})
    assert f["source"] == "estimated"
    assert f["etsy_fees"] > 0
