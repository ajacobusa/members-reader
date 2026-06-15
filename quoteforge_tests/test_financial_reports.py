"""Financial reporting expansion: Etsy fee-type breakdown (incl. Offsite Ads),
refund/cancellation rates, and traffic-source report - so you can see which
fees reduce profit and where sales originate."""
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_statement_csv_breaks_out_fee_types(tmp_path):
    csv_text = (
        "Date,Type,Title,Info,Amount,Fees & Taxes,Net\n"
        "2026-06-01,Sale,Order 3001,,52.21,,52.21\n"
        "2026-06-01,Fee,Listing fee,,,-0.20,-0.20\n"
        "2026-06-01,Fee,Transaction fee,,,-3.39,-3.39\n"
        "2026-06-01,Fee,Processing fee,,,-1.81,-1.81\n"
        "2026-06-01,Marketing,Offsite Ads Fee,,,-6.27,-6.27\n"
        "2026-06-02,Refund,Order 3002 refund,,-18.99,,-18.99\n")
    p = tmp_path / "etsy_statement.csv"
    p.write_text(csv_text, encoding="utf-8")
    from quoteforge.etsy.etsy_finance_import import import_statement_csv
    s = import_statement_csv(p)
    assert abs(s["listing"] - 0.20) < 0.01
    assert abs(s["transaction"] - 3.39) < 0.01
    assert abs(s["processing"] - 1.81) < 0.01
    assert abs(s["offsite_ads"] - 6.27) < 0.01      # the important one
    assert abs(s["refunds"] - 18.99) < 0.01


def test_report_revenue_matches_summarize_excludes_refunded():
    """REGRESSION: a refunded order is reversed revenue. summarize() and
    format_financial_report() must agree on revenue (both exclude refunded), so
    the report can't count a refund as revenue AND in the refund rate."""
    import re
    from quoteforge.etsy.financials import summarize
    from quoteforge.analytics.financial_reports import format_financial_report
    orders = [
        {"order_id": "D1", "status": "delivered", "sale_price": 50.0, "gelato_cost": 9.0},
        {"order_id": "R1", "status": "refunded", "sale_price": 50.0, "gelato_cost": 9.0},
    ]
    summ_rev = summarize(orders)["revenue"]
    m = re.search(r"Gross revenue:\s*\$([\d,]+\.\d{2})", format_financial_report(orders))
    report_rev = float(m.group(1).replace(",", ""))
    assert summ_rev == 50.0                 # only the delivered order counts
    assert report_rev == summ_rev           # report agrees (refunded excluded)


def test_fee_breakdown_shows_offsite_ads_pct():
    from quoteforge.analytics.financial_reports import fee_breakdown
    summary = {"listing": 0.20, "transaction": 3.39, "processing": 1.81,
               "offsite_ads": 6.27, "refunds": 18.99}
    r = fee_breakdown(summary, revenue=100.0)
    rows = {x["fee"]: x for x in r["rows"]}
    assert abs(rows["offsite_ads"]["pct_of_revenue"] - 6.27) < 0.01
    assert r["total_fees"] > 0


def test_refund_cancellation_rates(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    for i in range(7):
        db.create_order({"order_id": f"O{i}", "recipient_name": "A",
                         "occasion": "B", "sale_price": 20})
        db.update_order(f"O{i}", status="delivered")
    db.create_order({"order_id": "R1", "recipient_name": "A", "occasion": "B"})
    db.update_order("R1", status="refunded")
    db.create_order({"order_id": "C1", "recipient_name": "A", "occasion": "B"})
    db.update_order("C1", status="cancelled")
    db.create_order({"order_id": "C2", "recipient_name": "A", "occasion": "B"})
    db.update_order("C2", status="cancelled")
    from quoteforge.analytics.financial_reports import refund_cancellation_rates
    r = refund_cancellation_rates(db.get_all_orders(50))
    assert r["orders"] == 10
    assert abs(r["refund_rate_pct"] - 10.0) < 0.1
    assert abs(r["cancellation_rate_pct"] - 20.0) < 0.1


def test_traffic_source_report(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    for i, (src, sale) in enumerate([("offsite_ads", 50), ("etsy_search", 30),
                                     ("etsy_search", 30), ("direct", 20)]):
        db.create_order({"order_id": f"T{i}", "recipient_name": "A",
                         "occasion": "B", "sale_price": sale,
                         "acquisition_source": src})
        db.update_order(f"T{i}", status="delivered")
    from quoteforge.analytics.financial_reports import traffic_source_report
    rows = {r["source"]: r for r in traffic_source_report(db.get_all_orders(50))}
    assert rows["Etsy Search"]["orders"] == 2
    assert rows["Offsite Ads"]["orders"] == 1
    assert rows["Direct"]["orders"] == 1
