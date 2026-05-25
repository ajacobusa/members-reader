import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from stock_dashboard.engine.fetcher import fetch_stock_data, StockData

@pytest.fixture
def mock_ticker(mocker):
    ticker = MagicMock()
    ticker.info = {
        "longName": "Apple Inc", "sector": "Technology",
        "marketCap": 3_000_000_000_000, "averageVolume": 60_000_000,
        "trailingEps": 6.43, "forwardEps": 7.20,
        "trailingPE": 30.1, "profitMargins": 0.26,
        "recommendationKey": "buy", "targetMeanPrice": 220.0,
        "revenueGrowth": 0.09, "earningsGrowth": 0.11,
    }
    hist = pd.DataFrame({
        "Open": [190.0]*30, "High": [195.0]*30,
        "Low": [188.0]*30, "Close": [192.0]*30,
        "Volume": [60_000_000]*30,
    }, index=pd.date_range("2026-04-01", periods=30, freq="B"))
    ticker.history.return_value = hist
    ticker.news = [{"title": "Apple beats earnings", "link": "http://example.com"}]
    mocker.patch("yfinance.Ticker", return_value=ticker)
    return ticker

def test_fetch_returns_stock_data(mock_ticker):
    result = fetch_stock_data("AAPL")
    assert isinstance(result, StockData)
    assert result.ticker == "AAPL"
    assert result.company == "Apple Inc"

def test_fetch_market_cap_in_billions(mock_ticker):
    result = fetch_stock_data("AAPL")
    assert result.market_cap == pytest.approx(3_000.0, rel=0.01)

def test_fetch_price_history_has_30_rows(mock_ticker):
    result = fetch_stock_data("AAPL")
    assert len(result.price_history) == 30

def test_fetch_returns_none_on_exception(mocker):
    mocker.patch("yfinance.Ticker", side_effect=Exception("network error"))
    result = fetch_stock_data("BADTICKER")
    assert result is None

def test_fetch_includes_news_headlines(mock_ticker):
    result = fetch_stock_data("AAPL")
    assert len(result.news_headlines) >= 1
    assert "Apple beats earnings" in result.news_headlines[0]
