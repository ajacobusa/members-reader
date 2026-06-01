from stock_dashboard.engine.sources import fmp


def test_price_target_no_key():
    assert fmp.fetch_price_target("AAPL", "") is None


def test_price_target_parses_last_month_avg():
    fake = lambda *a, **k: [{"symbol": "AAPL", "lastMonthAvgPriceTarget": 329.88,
                             "lastQuarterAvgPriceTarget": 320.0}]
    assert fmp.fetch_price_target("AAPL", "KEY", get_fn=fake) == 329.88


def test_price_target_falls_back_to_quarter():
    fake = lambda *a, **k: [{"symbol": "AAPL", "lastMonthAvgPriceTarget": None,
                             "lastQuarterAvgPriceTarget": 320.0}]
    assert fmp.fetch_price_target("AAPL", "KEY", get_fn=fake) == 320.0


def test_recent_upgrade_true_on_grade_change_into_buy():
    fake = lambda *a, **k: [{"previousGrade": "Hold", "newGrade": "Buy"}]
    assert fmp.fetch_recent_upgrade("AAPL", "KEY", get_fn=fake) is True


def test_recent_upgrade_false_when_unchanged():
    fake = lambda *a, **k: [{"previousGrade": "Buy", "newGrade": "Buy"}]
    assert fmp.fetch_recent_upgrade("AAPL", "KEY", get_fn=fake) is False


def test_recent_upgrade_no_key():
    assert fmp.fetch_recent_upgrade("AAPL", "") is False


def test_earnings_surprise_uses_latest_reported():
    # newest row is future (null actual) and must be skipped
    fake = lambda *a, **k: [
        {"date": "2026-07-30", "epsActual": None, "epsEstimated": 1.86},
        {"date": "2026-04-30", "epsActual": 1.80, "epsEstimated": 1.50},
    ]
    assert fmp.fetch_latest_earnings_surprise_pct("AAPL", "KEY", get_fn=fake) == 20.0


def test_earnings_surprise_none_when_no_reported():
    fake = lambda *a, **k: [{"date": "2026-07-30", "epsActual": None, "epsEstimated": 1.86}]
    assert fmp.fetch_latest_earnings_surprise_pct("AAPL", "KEY", get_fn=fake) is None


def test_consensus_normalized():
    fake = lambda *a, **k: [{"consensus": "Strong Buy"}]
    assert fmp.fetch_consensus("AAPL", "KEY", get_fn=fake) == "strong_buy"


def test_consensus_no_key():
    assert fmp.fetch_consensus("AAPL", "") is None


def test_news_no_key():
    assert fmp.fetch_stock_news("AAPL", "") == []


def test_news_paid_endpoint_returns_empty_on_none():
    # http_get_json returns None on the 402; fetch should yield []
    fake = lambda *a, **k: None
    assert fmp.fetch_stock_news("AAPL", "KEY", get_fn=fake) == []
