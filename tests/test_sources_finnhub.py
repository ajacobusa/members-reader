from stock_dashboard.engine.sources import finnhub


def test_recommendation_no_key():
    assert finnhub.fetch_recommendation("AAPL", "") is None


def test_recommendation_picks_max():
    fake = lambda *a, **k: [{"strongBuy": 20, "buy": 5, "hold": 2, "sell": 0, "strongSell": 0}]
    assert finnhub.fetch_recommendation("AAPL", "KEY", get_fn=fake) == "strong_buy"


def test_news_sentiment_parses_bullish_percent():
    fake = lambda *a, **k: {"sentiment": {"bullishPercent": 0.72}}
    assert finnhub.fetch_news_sentiment("AAPL", "KEY", get_fn=fake) == 0.72


def test_company_news_titles():
    fake = lambda *a, **k: [{"headline": "Apple upgraded"}, {"headline": "Apple PT raised"}]
    out = finnhub.fetch_company_news("AAPL", "KEY", get_fn=fake)
    assert out == ["Apple upgraded", "Apple PT raised"]


def test_company_news_no_key():
    assert finnhub.fetch_company_news("AAPL", "") == []
