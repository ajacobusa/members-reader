"""Tests for financials, reconciliation export, and daily-report financials."""
from datetime import datetime
from unittest.mock import patch

from openpyxl import load_workbook

from quoteforge.etsy.financials import order_financials, summarize, month_financials


# ── Per-order financials ─────────────────────────────────────────

def test_order_financials_with_real_numbers():
    fin = order_financials({"order_id": "A", "sale_price": 29.99,
                            "gelato_cost": 11.0, "status": "shipped"})
    assert fin["sale_price"] == 29.99
    assert fin["gelato_cost"] == 11.0
    assert fin["estimated"] is False
    # net profit = sale - gelato - etsy fees, all > 0
    assert 0 < fin["net_profit"] < 29.99
    assert fin["etsy_fees"] > 0
    assert fin["sales_tax_collected"] > 0


def test_order_financials_falls_back_to_defaults():
    fin = order_financials({"order_id": "B", "status": "shipped"})  # no prices
    assert fin["estimated"] is True
    from quoteforge.config import DEFAULT_SALE_PRICE, DEFAULT_GELATO_COST
    assert fin["sale_price"] == DEFAULT_SALE_PRICE
    assert fin["gelato_cost"] == DEFAULT_GELATO_COST


def test_summarize_totals():
    orders = [
        {"order_id": "1", "sale_price": 30.0, "gelato_cost": 11.0, "status": "shipped"},
        {"order_id": "2", "sale_price": 45.0, "gelato_cost": 20.0, "status": "in_production"},
    ]
    s = summarize(orders)
    assert s["order_count"] == 2
    assert s["revenue"] == 75.0
    assert s["gelato_cost"] == 31.0
    assert s["net_profit"] > 0
    assert s["net_profit"] < s["revenue"]


def test_summarize_excludes_pending():
    orders = [
        {"order_id": "1", "sale_price": 30.0, "gelato_cost": 11.0, "status": "shipped"},
        {"order_id": "2", "sale_price": 30.0, "gelato_cost": 11.0, "status": "received"},
        {"order_id": "3", "sale_price": 30.0, "gelato_cost": 11.0, "status": "error"},
    ]
    s = summarize(orders, billable_only=True)
    assert s["order_count"] == 1  # only the shipped one counts as revenue


def test_sales_tax_is_separate_from_profit():
    fin = order_financials({"order_id": "T", "sale_price": 100.0,
                            "gelato_cost": 11.0, "status": "shipped"})
    # Tax is collected/remitted by Etsy — must NOT be folded into net profit
    assert fin["sales_tax_collected"] == 7.0  # 7% of 100
    assert fin["net_profit"] < 100.0 - 11.0   # profit excludes the tax pass-through


# ── Database integration ─────────────────────────────────────────

def test_create_order_stores_prices(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "P-1", "recipient_name": "Emma",
                         "occasion": "Graduation", "sale_price": 34.99,
                         "gelato_cost": 12.5})
        o = db.get_order("P-1")
    assert o["sale_price"] == 34.99
    assert o["gelato_cost"] == 12.5


def test_month_financials(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "M-1", "recipient_name": "X",
                               "occasion": "Y", "sale_price": 30.0, "gelato_cost": 11.0})
        db.update_order(oid, status="shipped")
        now = datetime.now()
        data = month_financials(now.year, now.month)
    assert data["order_count"] == 1
    assert data["revenue"] == 30.0


# ── Reconciliation Excel ─────────────────────────────────────────

def test_reconciliation_excel(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.etsy.reconciliation import export_reconciliation
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "RX-1", "recipient_name": "X",
                               "occasion": "Graduation", "sale_price": 30.0,
                               "gelato_cost": 11.0})
        db.update_order(oid, status="shipped")
        now = datetime.now()
        path = export_reconciliation(now.year, now.month, tmp_path / "recon.xlsx")
    assert path.exists()
    wb = load_workbook(path)
    ws = wb["Reconciliation"]
    # Header + at least one data row + totals row
    assert ws.max_row >= 4
    # A totals row exists
    found_total = any(ws.cell(row=r, column=1).value == "TOTAL"
                      for r in range(1, ws.max_row + 1))
    assert found_total


# ── Daily report includes financials ─────────────────────────────

def test_daily_report_has_financials(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.emailer import build_report_html
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "D-1", "recipient_name": "X",
                               "occasion": "Y", "sale_price": 30.0, "gelato_cost": 11.0})
        db.update_order(oid, status="shipped")
        _, body = build_report_html()
    assert "Revenue" in body
    assert "Etsy Fees" in body
    assert "NET PROFIT" in body
    assert "Gelato Print Cost" in body
    assert "Sales Tax" in body
