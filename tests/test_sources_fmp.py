from stock_dashboard.engine.sources import fmp


def test_price_target_no_key():
    assert fmp.fetch_price_target("AAPL", "") is None


def test_price_target_parses():
    fake = lambda *a, **k: [{"symbol": "AAPL", "targetConsensus": 250.0}]
    assert fmp.fetch_price_target("AAPL", "KEY", get_fn=fake) == 250.0


def test_recent_upgrade_true():
    fake = lambda *a, **k: [{"newGrade": "Buy", "previousGrade": "Hold"}]
    assert fmp.fetch_recent_upgrade("AAPL", "KEY", get_fn=fake) is True


def test_recent_upgrade_false_when_unchanged():
    fake = lambda *a, **k: [{"newGrade": "Hold", "previousGrade": "Hold"}]
    assert fmp.fetch_recent_upgrade("AAPL", "KEY", get_fn=fake) is False


def test_earnings_surprise_pct():
    fake = lambda *a, **k: [{"actualEarningResult": 6.0, "estimatedEarning": 5.0}]
    assert fmp.fetch_latest_earnings_surprise_pct("AAPL", "KEY", get_fn=fake) == 20.0


def test_stock_news_titles():
    fake = lambda *a, **k: [{"title": "Apple wins"}, {"title": "Apple climbs"}]
    assert fmp.fetch_stock_news("AAPL", "KEY", get_fn=fake) == ["Apple wins", "Apple climbs"]


def test_news_no_key():
    assert fmp.fetch_stock_news("AAPL", "") == []
