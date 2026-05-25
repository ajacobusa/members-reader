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
