import datetime

import pandas as pd
import pytest

from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.pipeline import run_pipeline
from stock_dashboard.engine.config_loader import load_config


def _history(n=60, trend="up"):
    prices = [100.0 + i * (0.5 if trend == "up" else -0.3) for i in range(n)]
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [5_000_000] * n,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="B"),
    )


def _make_stock(ticker="TEST", **kwargs):
    defaults = dict(
        ticker=ticker,
        company=f"{ticker} Inc",
        sector="Technology",
        market_cap=50.0,
        avg_volume=5_000_000,
        current_price=130.0,
        price_history=_history(),
        eps=5.0,
        eps_growth_yoy=0.15,
        revenue_growth_yoy=0.12,
        pe_ratio=25.0,
        profit_margin=0.20,
        analyst_rating="buy",
        analyst_target=150.0,
        news_headlines=[],
        catalysts=[],
    )
    defaults.update(kwargs)
    return StockData(**defaults)


@pytest.fixture
def mock_fetch(mocker):
    """Patch the fetcher so run_pipeline pulls synthetic stocks instead of yfinance."""
    return mocker.patch(
        "stock_dashboard.engine.fetcher.fetch_stock_data",
        side_effect=lambda ticker, *a, **k: _make_stock(ticker=ticker),
    )


def test_enriched_pipeline_to_db_roundtrip(config_path, mock_fetch):
    import datetime
    from stock_dashboard.db.database import Database
    cfg = load_config(config_path)
    # Lower the profit gate so synthetic survivors actually pass and we can verify
    # enrichment is populated end-to-end (not vacuously empty).
    cfg.probability_filter["min_composite_score"] = 0
    cfg.probability_filter["min_expected_return_pct"] = -100.0
    cfg.probability_filter["min_probability_gain"] = 0.0
    cfg.probability_filter["min_risk_reward"] = 0.0

    db = Database(":memory:")
    db.init_schema()
    today = datetime.date.today().isoformat()
    earnings = {t: {"date": today, "eps_actual": 6.0, "eps_estimate": 5.0}
                for t in ["AAPL", "MSFT", "NVDA", "META", "GOOGL"]}
    records, ok = run_pipeline(
        tickers=["AAPL", "MSFT", "NVDA", "META", "GOOGL"], cfg=cfg,
        market_data={"vix": 16.0, "spy_vs_50sma": 0.05, "fear_greed": 65},
        earnings_data=earnings, sector_pe_map={"Technology": 28.0},
        marked_picks_count=0,
    )
    assert ok is True
    assert len(records) > 0  # gate lowered → at least one pick flows through
    db.save_picks(records)
    saved = db.get_picks()
    assert len(saved) == len(records)
    for s in saved:
        assert s["suggested_size_pct"] is not None
        assert s["expected_return_pct"] is not None
        assert s["prob_gain"] is not None
