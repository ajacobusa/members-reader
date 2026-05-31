import pytest
import datetime
import pandas as pd
from stock_dashboard.engine.pipeline import gate1_quality, gate2_market, gate3_catalyst, gate4_technical, run_pipeline
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import load_config

def _history(n=60, trend="up"):
    prices = [100.0 + i * (0.5 if trend == "up" else -0.3) for i in range(n)]
    return pd.DataFrame({
        "Open": prices, "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices], "Close": prices,
        "Volume": [5_000_000] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="B"))

def _stock(**kwargs):
    defaults = dict(
        ticker="TEST", company="Test Co", sector="Technology",
        market_cap=50.0, avg_volume=5_000_000, current_price=130.0,
        price_history=_history(), eps=5.0, eps_growth_yoy=0.15,
        revenue_growth_yoy=0.12, pe_ratio=25.0, profit_margin=0.20,
        analyst_rating="buy", analyst_target=150.0,
        news_headlines=[], catalysts=[],
    )
    defaults.update(kwargs)
    return StockData(**defaults)

def test_gate1_passes_large_cap_profitable(config_path):
    cfg = load_config(config_path)
    stock = _stock(market_cap=50.0, avg_volume=5_000_000, eps=5.0)
    assert gate1_quality(stock, cfg) is True

def test_gate1_rejects_small_cap(config_path):
    cfg = load_config(config_path)
    stock = _stock(market_cap=2.0)
    assert gate1_quality(stock, cfg) is False

def test_gate1_rejects_unprofitable(config_path):
    cfg = load_config(config_path)
    stock = _stock(eps=-1.0)
    assert gate1_quality(stock, cfg) is False

def test_gate3_passes_with_earnings_catalyst(config_path):
    cfg = load_config(config_path)
    stock = _stock()
    recent_date = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    result = gate3_catalyst(stock, cfg, earnings_data={
        "TEST": {"eps_actual": 6.0, "eps_estimate": 5.0, "date": recent_date}
    })
    assert result is True
    assert any(c["type"] == "earnings_beat" for c in stock.catalysts)

def test_gate3_rejects_no_catalyst(config_path):
    cfg = load_config(config_path)
    stock = _stock()
    result = gate3_catalyst(stock, cfg, earnings_data={})
    assert result is False

def test_gate4_passes_good_technicals(config_path):
    cfg = load_config(config_path)
    stock = _stock()
    assert gate4_technical(stock, cfg) is True

def test_gate4_rejects_below_20sma(config_path):
    cfg = load_config(config_path)
    stock = _stock(price_history=_history(trend="down"), current_price=82.0)
    assert gate4_technical(stock, cfg) is False

def test_run_pipeline_aborts_on_bad_market(config_path, mocker):
    cfg = load_config(config_path)
    mocker.patch("stock_dashboard.engine.fetcher.fetch_stock_data", return_value=None)
    records, market_ok = run_pipeline(
        tickers=["AAPL"],
        cfg=cfg,
        market_data={"vix": 50.0, "spy_vs_50sma": -0.05, "fear_greed": 10},
        earnings_data={},
        sector_pe_map={},
        marked_picks_count=0,
    )
    assert market_ok is False
    assert records == []

def test_run_pipeline_enriches_and_profit_gates(config_path):
    cfg = load_config(config_path)
    import datetime
    today = datetime.date.today().isoformat()

    def fake_fetch(ticker):
        return _stock(ticker=ticker, market_cap=50.0, avg_volume=5_000_000)

    records, market_ok = run_pipeline(
        tickers=["TEST"], cfg=cfg,
        market_data={"vix": 16.0, "spy_vs_50sma": 0.05, "fear_greed": 65},
        earnings_data={"TEST": {"eps_actual": 6.0, "eps_estimate": 5.0, "date": today}},
        sector_pe_map={"Technology": 28.0}, marked_picks_count=0,
        fetch_fn=fake_fetch,
    )
    assert market_ok is True
    # any emitted record must carry enrichment fields
    for r in records:
        assert r.expected_return_pct is not None
        assert r.suggested_size_pct is not None


def test_upside_mode_includes_stocks_without_catalyst(config_path):
    cfg = load_config(config_path)
    cfg.ranking["require_catalyst"] = False          # upside bucket mode
    # relax profit gate so survivors flow through to records for assertion
    cfg.probability_filter["min_composite_score"] = 0
    cfg.probability_filter["min_expected_return_pct"] = -100.0
    cfg.probability_filter["min_probability_gain"] = 0.0
    cfg.probability_filter["min_risk_reward"] = 0.0

    def fake_fetch(ticker):
        # a clean quality+uptrend stock but with NO catalyst (empty earnings_data,
        # normal volume, not at 52w high, no upgrade news)
        return _stock(ticker=ticker, market_cap=50.0, avg_volume=5_000_000,
                      news_headlines=[])

    records, ok = run_pipeline(
        tickers=["TEST"], cfg=cfg,
        market_data={"vix": 16.0, "spy_vs_50sma": 0.05, "fear_greed": 65},
        earnings_data={}, sector_pe_map={"Technology": 28.0},
        marked_picks_count=0, fetch_fn=fake_fetch,
    )
    assert ok is True
    assert len(records) >= 1     # no-catalyst stock still ranked in upside mode


def test_catalyst_mode_still_excludes_no_catalyst(config_path):
    cfg = load_config(config_path)  # default require_catalyst: true
    cfg.probability_filter["min_composite_score"] = 0
    cfg.probability_filter["min_expected_return_pct"] = -100.0
    cfg.probability_filter["min_probability_gain"] = 0.0
    cfg.probability_filter["min_risk_reward"] = 0.0

    def fake_fetch(ticker):
        return _stock(ticker=ticker, market_cap=50.0, avg_volume=5_000_000,
                      news_headlines=[])

    records, ok = run_pipeline(
        tickers=["TEST"], cfg=cfg,
        market_data={"vix": 16.0, "spy_vs_50sma": 0.05, "fear_greed": 65},
        earnings_data={}, sector_pe_map={"Technology": 28.0},
        marked_picks_count=0, fetch_fn=fake_fetch,
    )
    # strict mode: no catalyst -> dropped at gate3 -> empty
    assert records == []
