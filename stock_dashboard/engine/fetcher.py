import logging
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

@dataclass
class StockData:
    ticker: str
    company: str
    sector: str
    market_cap: float
    avg_volume: float
    current_price: float
    price_history: pd.DataFrame
    eps: Optional[float]
    eps_growth_yoy: Optional[float]
    revenue_growth_yoy: Optional[float]
    pe_ratio: Optional[float]
    profit_margin: Optional[float]
    analyst_rating: Optional[str]
    analyst_target: Optional[float]
    news_headlines: list[str] = field(default_factory=list)
    catalysts: list[dict] = field(default_factory=list)
    sentiment_score: Optional[float] = None

def fetch_stock_data(ticker: str, period: str = "3mo") -> Optional[StockData]:
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period=period)
        if hist.empty:
            return None
        news = [n.get("title", "") for n in (t.news or [])[:10]]
        return StockData(
            ticker=ticker,
            company=info.get("longName", ticker),
            sector=info.get("sector", "Unknown"),
            market_cap=(info.get("marketCap") or 0) / 1e9,
            avg_volume=info.get("averageVolume") or 0,
            current_price=hist["Close"].iloc[-1],
            price_history=hist,
            eps=info.get("trailingEps"),
            eps_growth_yoy=info.get("earningsGrowth"),
            revenue_growth_yoy=info.get("revenueGrowth"),
            pe_ratio=info.get("trailingPE"),
            profit_margin=info.get("profitMargins"),
            analyst_rating=info.get("recommendationKey"),
            analyst_target=info.get("targetMeanPrice"),
            news_headlines=news,
        )
    except Exception as exc:
        log.warning("fetch_stock_data(%s) failed: %s", ticker, exc)
        return None
