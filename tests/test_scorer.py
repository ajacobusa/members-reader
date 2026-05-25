import pytest
import pandas as pd
import numpy as np
from stock_dashboard.engine.scorer import score_stock, ScoreResult
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import load_config

def _make_history(close_prices, volumes=None):
    n = len(close_prices)
    volumes = volumes or [5_000_000] * n
    return pd.DataFrame({
        "Open": close_prices, "High": [p * 1.01 for p in close_prices],
        "Low": [p * 0.99 for p in close_prices],
        "Close": close_prices, "Volume": volumes,
    }, index=pd.date_range("2026-01-01", periods=n, freq="B"))

def _make_stock(ticker="AAPL", close_prices=None, volumes=None, **kwargs):
    prices = close_prices or [100.0 + i * 0.5 for i in range(60)]
    vols = volumes or [5_000_000] * len(prices)
    defaults = dict(
        company="Test Co", sector="Technology", market_cap=500.0,
        avg_volume=5_000_000, current_price=prices[-1],
        price_history=_make_history(prices, vols),
        eps=5.0, eps_growth_yoy=0.15, revenue_growth_yoy=0.12,
        pe_ratio=25.0, profit_margin=0.20,
        analyst_rating="buy", analyst_target=130.0,
        news_headlines=[], catalysts=[],
    )
    defaults.update(kwargs)
    return StockData(ticker=ticker, **defaults)

def test_score_returns_score_result(config_path):
    cfg = load_config(config_path)
    stock = _make_stock()
    result = score_stock(stock, cfg, sector_pe_map={"Technology": 28.0}, marked_picks_count=0)
    assert isinstance(result, ScoreResult)

def test_composite_score_in_range(config_path):
    cfg = load_config(config_path)
    stock = _make_stock()
    result = score_stock(stock, cfg, sector_pe_map={"Technology": 28.0}, marked_picks_count=0)
    assert 0 <= result.composite <= 100

def test_strong_fundamentals_score_higher(config_path):
    cfg = load_config(config_path)
    good = _make_stock(eps_growth_yoy=0.40, revenue_growth_yoy=0.35,
                       profit_margin=0.35, analyst_rating="strongBuy")
    bad = _make_stock(eps_growth_yoy=-0.10, revenue_growth_yoy=-0.05,
                      profit_margin=0.05, analyst_rating="sell")
    good_r = score_stock(good, cfg, sector_pe_map={}, marked_picks_count=0)
    bad_r = score_stock(bad, cfg, sector_pe_map={}, marked_picks_count=0)
    assert good_r.fundamental > bad_r.fundamental

def test_pattern_score_zero_when_insufficient_history(config_path):
    cfg = load_config(config_path)
    stock = _make_stock()
    result = score_stock(stock, cfg, sector_pe_map={}, marked_picks_count=5)
    assert result.pattern_score == 0.0

def test_signals_dict_populated(config_path):
    cfg = load_config(config_path)
    stock = _make_stock()
    result = score_stock(stock, cfg, sector_pe_map={}, marked_picks_count=0)
    assert "rsi" in result.signals
    assert "macd_bullish" in result.signals
