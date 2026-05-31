import numpy as np
import pandas as pd
import pytest
from stock_dashboard.engine.statistics import (
    move_distribution, kelly_fraction, confidence_interval, build_profile,
    ProbabilityProfile,
)
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import load_config


def _stock(returns):
    prices = [100.0]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    hist = pd.DataFrame({
        "Open": prices, "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices], "Close": prices,
        "Volume": [5_000_000] * len(prices),
    }, index=pd.date_range("2026-01-01", periods=len(prices), freq="B"))
    return StockData(
        ticker="TST", company="Test", sector="Technology", market_cap=50.0,
        avg_volume=5_000_000, current_price=prices[-1], price_history=hist,
        eps=5.0, eps_growth_yoy=0.15, revenue_growth_yoy=0.12, pe_ratio=25.0,
        profit_margin=0.2, analyst_rating="buy", analyst_target=150.0,
        news_headlines=[], catalysts=[],
    )


def test_move_distribution_basic_math():
    returns = [0.02] * 6 + [-0.01] * 4
    d = move_distribution(pd.Series(returns))
    assert d["prob_gain"] == pytest.approx(0.6, abs=1e-6)
    assert d["avg_gain_pct"] == pytest.approx(2.0, abs=1e-6)
    assert d["avg_loss_pct"] == pytest.approx(1.0, abs=1e-6)
    assert d["expected_return_pct"] == pytest.approx(0.8, abs=1e-6)


def test_kelly_fraction_positive_edge():
    assert kelly_fraction(0.6, 2.0, 1.0) == pytest.approx(0.4, abs=1e-6)


def test_kelly_fraction_zero_when_no_loss_data():
    assert kelly_fraction(0.6, 2.0, 0.0) == 0.0


def test_confidence_interval_orders_low_high():
    low, high = confidence_interval(1.0, 2.0, 1.5)
    assert low < 1.0 < high
    assert low == pytest.approx(1.0 - 3.0)
    assert high == pytest.approx(1.0 + 3.0)


def test_build_profile_returns_dataclass(config_path):
    cfg = load_config(config_path)
    stock = _stock([0.02] * 6 + [-0.01] * 4)
    p = build_profile(stock, cfg)
    assert isinstance(p, ProbabilityProfile)
    assert 0.0 <= p.prob_gain <= 1.0
    assert p.ci_low_pct <= p.expected_return_pct <= p.ci_high_pct


def test_build_profile_insufficient_data_is_safe(config_path):
    cfg = load_config(config_path)
    stock = _stock([0.01])
    p = build_profile(stock, cfg)
    assert isinstance(p, ProbabilityProfile)
    assert p.sample_size >= 0


def test_earnings_beat_rate_capped_at_quarters(config_path):
    from stock_dashboard.engine.statistics import _earnings_stats
    class S:  # minimal stub with the attribute
        earnings_history = [{"actual": 2.0, "estimate": 1.0, "move_pct": 3.0}] * 10
    out = _earnings_stats(S(), quarters=8)
    assert out["n"] == 8
    assert out["beat_rate"] == 1.0
