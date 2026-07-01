"""Accounting correctness: tax-exclusive payout (no double-count), Gelato shipping
in COGS, refund/return parity between the daily ledger and the period summary, and
the bookkeeper/QuickBooks CSV export.
"""
import sqlite3

import pytest

from quoteforge.etsy.financials import order_financials, summarize


def _etsy_order(**over):
    # Etsy grand-total order: sale_price INCLUDES shipping + tax.
    o = {"order_id": "o1", "etsy_order_id": "E1", "status": "shipped",
         "created_at": "2026-06-10", "occasion": "birthday",
         "sale_price": 43.20, "tax_collected": 3.20, "shipping_collected": 5.00,
         "gelato_cost": 13.00, "etsy_fees_actual": 2.60}
    o.update(over)
    return o


# ── payout: no shipping double-count, tax excluded ─────────────────────────
def test_etsy_payout_excludes_tax_and_does_not_double_count_shipping():
    f = order_financials(_etsy_order())
    # product revenue is tax-exclusive (item + shipping): 43.20 - 3.20
    assert f["product_revenue"] == 40.00
    # REGRESSION: payout = product_revenue - fees (NOT sale_price + shipping - fees,
    # which double-counted shipping and left tax in -> 45.60).
    assert f["net_payout"] == round(40.00 - 2.60, 2) == 37.40
    # a per-order entry now balances: payout + fees == income
    assert round(f["net_payout"] + f["etsy_fees"], 2) == f["product_revenue"]


def test_direct_sale_keeps_shipping_as_income():
    # No tax recorded => sale_price is the pre-shipping subtotal; shipping is extra.
    f = order_financials({"order_id": "d1", "status": "shipped",
                          "created_at": "2026-06-10", "occasion": "birthday",
                          "sale_price": 35.00, "shipping_collected": 5.00,
                          "gelato_cost": 13.00, "etsy_fees_actual": 2.60})
    assert f["product_revenue"] == 35.00
    assert f["net_payout"] == round(35.00 + 5.00 - 2.60, 2) == 37.40


# ── Gelato shipping is part of COGS ────────────────────────────────────────
def test_gelato_shipping_counts_as_cogs():
    base = order_financials(_etsy_order())
    withship = order_financials(_etsy_order(shipping_cost=6.25))
    assert withship["gelato_shipping"] == 6.25
    # net profit drops by exactly the Gelato shipping charge
    assert round(base["net_profit"] - withship["net_profit"], 2) == 6.25


def test_summarize_totals_payout_and_gelato_shipping():
    s = summarize([_etsy_order(shipping_cost=6.25)])
    assert s["net_payout"] == 37.40
    assert s["gelato_shipping"] == 6.25
    assert s["gelato_cost"] == 13.00


# ── refund/return parity: ledger must agree with summarize ─────────────────
@pytest.fixture
def db(tmp_path, monkeypatch):
    import quoteforge.db.database as d
    monkeypatch.setattr(d, "DB_PATH", tmp_path / "t.db")
    d.init_db()
    return d


def _insert(d, oid, status, sale, **extra):
    from datetime import datetime
    conn = sqlite3.connect(d.DB_PATH)
    _cm = datetime.now().strftime("%Y-%m-%d")            # TODAY (current month, not future)
    cols = {"order_id": oid, "recipient_name": "R", "occasion": "birthday",
            "status": status, "sale_price": sale, "created_at": _cm,
            "gelato_cost": 13.00, "tax_collected": 3.20, "shipping_collected": 5.00,
            "etsy_fees_actual": 2.60, **extra}
    conn.execute(f"INSERT INTO orders ({','.join(cols)}) "
                 f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    conn.commit()
    conn.close()


def test_refunded_order_excluded_from_daily_ledger(db):
    # REGRESSION: a refunded order kept full revenue + COGS in the daily P&L while
    # summarize() excluded it -> the two layers reported different net profit.
    _insert(db, "good", "shipped", 43.20)
    _insert(db, "refunded", "refunded", 43.20)
    from quoteforge.etsy.ledger import build_ledger
    from quoteforge.etsy.financials import month_financials
    from datetime import datetime as _dt
    led = build_ledger("month")
    summ = month_financials(_dt.now().year, _dt.now().month)   # current month (matches ledger)
    # exactly one billable order in both layers, identical revenue
    assert summ["order_count"] == 1
    assert round(led["totals"]["revenue"], 2) == round(summ["revenue"], 2) == 40.00


# ── bookkeeper / QuickBooks CSV ────────────────────────────────────────────
def test_books_export_balances_and_writes(db, tmp_path):
    _insert(db, "o1", "shipped", 43.20)
    _insert(db, "o2", "delivered", 43.20, shipping_cost=6.25)
    from quoteforge.etsy.books_export import books_summary, write_books_csv, COLUMNS
    s = books_summary("month")
    assert s["order_count"] == 2 and s["balances"] is True
    assert s["gelato_cogs"] == round(13.00 + (13.00 + 6.25), 2)        # COGS incl. shipping
    assert s["sales_tax_passthrough"] == 6.40                          # 2 x 3.20, pass-through
    out = write_books_csv(tmp_path / "books.csv", "month")
    text = out.read_text(encoding="utf-8")
    assert ",".join(COLUMNS) in text and "TOTAL" in text
    assert text.count("\n") >= 4                                       # header+2 orders+total


def test_books_export_emails_csv_to_address(db, tmp_path, monkeypatch):
    # REGRESSION: `books-export ... <address>` sends the CSV to that inbox (Wave/QBO).
    _insert(db, "o1", "shipped", 43.20)
    import quoteforge.automation.emailer as em
    seen = {}

    def _fake(subject, body, to="", attachments=None):
        seen.update(to=to, attachments=attachments, subject=subject)
        return {"status": "sent", "to": to, "bcc": "owner@x"}
    monkeypatch.setattr(em, "_send_email", _fake)
    from quoteforge import admin
    rc = admin.main(["books-export", "month", str(tmp_path / "b.csv"),
                     "joffielsc@gmail.com"])
    assert rc == 0
    assert seen["to"] == "joffielsc@gmail.com"
    assert seen["attachments"] and str(seen["attachments"][0]).endswith(".csv")
