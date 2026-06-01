from dataclasses import asdict

from stock_dashboard.engine.sources.aggregator import aggregate, AggregatedData


class _FakeCache:
    def __init__(self):
        self.store = {}
    def get(self, ticker, kind):
        return self.store.get((ticker, kind))
    def set(self, ticker, kind, value):
        self.store[(ticker, kind)] = value


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


def test_aggregate_uses_cache_hit_without_calling_providers(mocker):
    from stock_dashboard.engine.sources import aggregator
    spy = mocker.patch.object(aggregator.fmp, "fetch_price_target")
    cache = _FakeCache()
    cache.set("AAPL", "aggregate", {
        "headlines": ["cached"], "analyst_target": 200.0, "recent_upgrade": True,
        "news_sentiment": 0.5, "earnings_surprise_pct": 9.0, "sources_used": ["fmp"]})
    out = aggregator.aggregate("AAPL", "Apple",
                               api_keys={"fmp": "k", "finnhub": "", "newsapi": ""},
                               cache=cache)
    assert out.headlines == ["cached"]
    assert out.analyst_target == 200.0
    spy.assert_not_called()  # cache hit -> no provider calls


def test_aggregate_includes_finnhub_consensus(mocker):
    from stock_dashboard.engine.sources import aggregator
    mocker.patch.object(aggregator.finnhub, "fetch_recommendation", return_value="strong_buy")
    mocker.patch.object(aggregator.finnhub, "fetch_company_news", return_value=[])
    mocker.patch.object(aggregator.finnhub, "fetch_news_sentiment", return_value=None)
    mocker.patch.object(aggregator.newsapi, "fetch_headlines", return_value=[])
    mocker.patch.object(aggregator.fmp, "fetch_stock_news", return_value=[])
    mocker.patch.object(aggregator.fmp, "fetch_price_target", return_value=None)
    mocker.patch.object(aggregator.fmp, "fetch_recent_upgrade", return_value=False)
    mocker.patch.object(aggregator.fmp, "fetch_latest_earnings_surprise_pct", return_value=None)
    out = aggregator.aggregate("AAPL", "Apple",
                               api_keys={"finnhub": "k", "fmp": "", "newsapi": ""})
    assert out.analyst_consensus == "strong_buy"
    assert "finnhub" in out.sources_used


def test_aggregate_consensus_none_without_finnhub_key(mocker):
    from stock_dashboard.engine.sources import aggregator
    out = aggregator.aggregate("AAPL", "Apple",
                               api_keys={"finnhub": "", "fmp": "", "newsapi": ""})
    assert out.analyst_consensus is None


def test_aggregate_populates_cache_on_miss(mocker):
    from stock_dashboard.engine.sources import aggregator
    mocker.patch.object(aggregator.fmp, "fetch_price_target", return_value=250.0)
    mocker.patch.object(aggregator.fmp, "fetch_recent_upgrade", return_value=False)
    mocker.patch.object(aggregator.fmp, "fetch_latest_earnings_surprise_pct", return_value=None)
    mocker.patch.object(aggregator.fmp, "fetch_stock_news", return_value=[])
    mocker.patch.object(aggregator.finnhub, "fetch_company_news", return_value=[])
    mocker.patch.object(aggregator.finnhub, "fetch_news_sentiment", return_value=None)
    mocker.patch.object(aggregator.newsapi, "fetch_headlines", return_value=[])
    cache = _FakeCache()
    out = aggregator.aggregate("MSFT", "Microsoft",
                               api_keys={"fmp": "k", "finnhub": "", "newsapi": ""},
                               cache=cache)
    assert out.analyst_target == 250.0
    stored = cache.get("MSFT", "aggregate")
    assert stored is not None and stored["analyst_target"] == 250.0
