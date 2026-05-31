from stock_dashboard.engine.sources.aggregator import aggregate, AggregatedData


def test_no_keys_returns_empty():
    out = aggregate("AAPL", "Apple", api_keys={"newsapi": "", "fmp": "", "finnhub": ""})
    assert isinstance(out, AggregatedData)
    assert out.headlines == []
    assert out.sources_used == []
    assert out.analyst_target is None


def test_merges_providers(mocker):
    mocker.patch("stock_dashboard.engine.sources.aggregator.newsapi.fetch_headlines",
                 return_value=["NewsAPI hl"])
    mocker.patch("stock_dashboard.engine.sources.aggregator.finnhub.fetch_company_news",
                 return_value=["Finnhub hl"])
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_stock_news",
                 return_value=["FMP hl"])
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_price_target",
                 return_value=250.0)
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_recent_upgrade",
                 return_value=True)
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_latest_earnings_surprise_pct",
                 return_value=12.0)
    mocker.patch("stock_dashboard.engine.sources.aggregator.finnhub.fetch_news_sentiment",
                 return_value=0.7)
    out = aggregate("AAPL", "Apple",
                    api_keys={"newsapi": "k", "fmp": "k", "finnhub": "k"})
    assert "NewsAPI hl" in out.headlines and "Finnhub hl" in out.headlines and "FMP hl" in out.headlines
    assert out.analyst_target == 250.0
    assert out.recent_upgrade is True
    assert out.earnings_surprise_pct == 12.0
    assert out.news_sentiment == 0.7
    assert set(out.sources_used) >= {"newsapi", "finnhub", "fmp"}


def test_dedupes_headlines(mocker):
    mocker.patch("stock_dashboard.engine.sources.aggregator.newsapi.fetch_headlines",
                 return_value=["same", "a"])
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_stock_news",
                 return_value=["same", "b"])
    mocker.patch("stock_dashboard.engine.sources.aggregator.finnhub.fetch_company_news",
                 return_value=[])
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_price_target", return_value=None)
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_recent_upgrade", return_value=False)
    mocker.patch("stock_dashboard.engine.sources.aggregator.fmp.fetch_latest_earnings_surprise_pct", return_value=None)
    mocker.patch("stock_dashboard.engine.sources.aggregator.finnhub.fetch_news_sentiment", return_value=None)
    out = aggregate("AAPL", "Apple", api_keys={"newsapi": "k", "fmp": "k", "finnhub": ""})
    assert out.headlines.count("same") == 1
