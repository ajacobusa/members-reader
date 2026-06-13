"""CLV gaps closed: average time between purchases, days since last order, and
a lapsed-customer win-back list (repeat-friendly: re-engage the cheapest
profit there is)."""
from datetime import datetime, timedelta


def _ago(days):
    return (datetime.now() - timedelta(days=days)).isoformat()


def test_clv_reports_time_between_purchases():
    orders = [
        {"customer_email": "a@b.com", "sale_price": 20, "created_at": _ago(60)},
        {"customer_email": "a@b.com", "sale_price": 20, "created_at": _ago(30)},
    ]
    from quoteforge.analytics.clv import build_clv
    clv = build_clv(orders)
    # ~30 days between the two orders
    assert 25 <= clv["avg_days_between_orders"] <= 35
    a = clv["top_customers"][0]
    assert 25 <= a["avg_days_between"] <= 35


def test_lapsed_customer_surfaces_in_winback():
    orders = [
        # repeat customer, last order 120 days ago -> lapsed
        {"customer_email": "lapsed@b.com", "sale_price": 40, "created_at": _ago(200)},
        {"customer_email": "lapsed@b.com", "sale_price": 40, "created_at": _ago(120)},
        # recent customer -> NOT win-back
        {"customer_email": "active@b.com", "sale_price": 30, "created_at": _ago(10)},
    ]
    from quoteforge.analytics.clv import build_clv
    clv = build_clv(orders)
    emails = [w["email"] for w in clv["winback"]]
    assert "lapsed@b.com" in emails
    assert "active@b.com" not in emails


def test_clv_median_and_predicted_next():
    """Median days between orders + a predicted next-purchase date per repeat
    customer, plus a 'due soon' list for pre-emptive outreach."""
    from quoteforge.analytics.clv import build_clv
    # 3 orders ~30 days apart; last ~28 days ago -> next due in ~2 days
    orders = [
        {"customer_email": "r@b.com", "sale_price": 20, "created_at": _ago(88)},
        {"customer_email": "r@b.com", "sale_price": 20, "created_at": _ago(58)},
        {"customer_email": "r@b.com", "sale_price": 20, "created_at": _ago(28)},
    ]
    clv = build_clv(orders)
    assert "median_days_between_orders" in clv
    c = clv["top_customers"][0]
    assert 25 <= c["median_days_between"] <= 35
    assert c["predicted_next"]                      # a date string
    # within the default due-soon window -> surfaced for pre-emptive outreach
    assert any(d["email"] == "r@b.com" for d in clv["due_soon"])


def test_no_orders_safe():
    from quoteforge.analytics.clv import build_clv
    clv = build_clv([])
    assert clv["customers"] == 0 and clv["winback"] == []
    assert clv["avg_days_between_orders"] == 0
    assert clv["due_soon"] == []
