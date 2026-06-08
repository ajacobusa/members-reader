"""CLV dashboard + performance-ranked quote library (real data only)."""
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


def test_clv_empty_when_no_orders(fresh_db):
    from quoteforge.analytics.clv import build_clv, format_clv_text
    c = build_clv()
    assert c["customers"] == 0 and c["avg_clv"] == 0.0
    assert "No orders yet" in format_clv_text(c)


def test_clv_aggregates_real_orders(fresh_db):
    db = fresh_db
    db.create_order({"order_id": "A1", "customer_email": "x@y.com",
                     "customer_name": "Pat", "sale_price": 50.0, "occasion": "Wedding"})
    db.create_order({"order_id": "A2", "customer_email": "x@y.com",
                     "customer_name": "Pat", "sale_price": 30.0, "occasion": "Birthday"})
    db.create_order({"order_id": "B1", "customer_email": "z@y.com",
                     "customer_name": "Sam", "sale_price": 20.0, "occasion": "Wedding"})
    from quoteforge.analytics.clv import build_clv
    c = build_clv()
    assert c["customers"] == 2 and c["total_revenue"] == 100.0
    assert c["avg_clv"] == 50.0 and c["repeat_customers"] == 1
    assert c["top_customers"][0]["revenue"] == 80.0


def test_quote_ranking_falls_back_without_sales(fresh_db):
    from quoteforge.quotes.performance import ranked_categories
    from quoteforge.quotes.library import QUOTE_LIBRARY
    assert set(ranked_categories()) == set(QUOTE_LIBRARY.keys())


def test_quote_performance_uses_real_sales(fresh_db):
    db = fresh_db
    for i in range(3):
        db.create_order({"order_id": f"W{i}", "customer_email": f"a{i}@y.com",
                         "sale_price": 40.0, "occasion": "Wedding", "tone": "Elegant"})
    from quoteforge.quotes.performance import theme_performance
    perf = theme_performance()
    assert perf and perf[0]["occasion"] == "Wedding" and perf[0]["orders"] == 3


def test_clv_and_quoteperf_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "clv" in COMMANDS and "quote-performance" in COMMANDS
