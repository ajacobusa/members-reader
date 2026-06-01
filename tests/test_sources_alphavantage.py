from stock_dashboard.engine.sources import alphavantage as av


def test_sentiment_no_key():
    assert av.fetch_sentiment("AAPL", "") is None


def test_sentiment_averages_ticker_scores_and_normalizes():
    fake = lambda *a, **k: {"feed": [
        {"ticker_sentiment": [{"ticker": "AAPL", "ticker_sentiment_score": "0.34"}]},
        {"ticker_sentiment": [{"ticker": "AAPL", "ticker_sentiment_score": "0.10"}]},
        {"ticker_sentiment": [{"ticker": "MSFT", "ticker_sentiment_score": "0.9"}]},
    ]}
    # avg of AAPL scores = (0.34+0.10)/2 = 0.22 ; normalized (x+1)/2 = 0.61
    assert av.fetch_sentiment("AAPL", "KEY", get_fn=fake) == 0.61


def test_sentiment_rate_limited_returns_none():
    fake = lambda *a, **k: {"Note": "Thank you for using Alpha Vantage! rate limit"}
    assert av.fetch_sentiment("AAPL", "KEY", get_fn=fake) is None


def test_headlines_no_key():
    assert av.fetch_headlines("AAPL", "") == []


def test_headlines_parses_titles():
    fake = lambda *a, **k: {"feed": [{"title": "Apple beats"}, {"title": "Apple climbs"}]}
    assert av.fetch_headlines("AAPL", "KEY", get_fn=fake) == ["Apple beats", "Apple climbs"]
