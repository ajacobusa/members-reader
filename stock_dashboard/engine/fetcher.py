import logging
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import yfinance as yf
from stock_dashboard.engine.sources import stooq, fmp

log = logging.getLogger(__name__)

# Price-data fallback chain when yfinance is down: Stooq (free, no key) then
# FMP (uses the configured key). configure_fallback() is called once per run by
# the pipeline so the per-ticker fetch (which only receives a ticker) can reach
# the keys without a signature change.
_FALLBACK_KEYS: dict = {}


def configure_fallback(api_keys: dict) -> None:
    """Register API keys for the price fallback chain. Call once before fetching."""
    global _FALLBACK_KEYS
    _FALLBACK_KEYS = api_keys or {}

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
            raise ValueError("empty yfinance history")
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
        log.warning("fetch_stock_data(%s) yfinance failed: %s — trying fallbacks", ticker, exc)
        _note_yfinance_error(exc)
        return _fetch_via_fallback(ticker, period)


def _note_yfinance_error(exc: Exception) -> None:
    """If yfinance failed due to rate limiting, mark it cooling so we stop
    hammering it and prefer the fallbacks for the rest of the run."""
    from stock_dashboard.engine import ratelimit
    guard = ratelimit.get_guard()
    if not guard:
        return
    msg = str(exc).lower()
    if "429" in msg or "too many request" in msg or "rate limit" in msg:
        guard.mark("yfinance", reason="yfinance rate limited")


def _fetch_via_fallback(ticker: str, period: str) -> Optional[StockData]:
    """Price-only fallback when yfinance is down. Tries Stooq (free, no key)
    then FMP (configured key). Keeps the ticker alive in the pipeline (technical
    + volume gates still run); fundamentals are left None so fundamental gates
    simply don't fire rather than the stock vanishing entirely."""
    hist, source = stooq.fetch_price_history(ticker, period), "stooq"
    if hist is None or hist.empty:
        hist, source = fmp.fetch_price_history(ticker, _FALLBACK_KEYS.get("fmp", ""), period), "fmp"
    if hist is None or hist.empty:
        log.warning("fetch_stock_data(%s) failed: all price fallbacks empty", ticker)
        return None
    avg_vol = float(hist["Volume"].tail(20).mean()) if "Volume" in hist else 0.0
    log.info("fetch_stock_data(%s) served from %s fallback (%d bars)", ticker, source, len(hist))
    return StockData(
        ticker=ticker,
        company=ticker,
        sector="Unknown",
        market_cap=0.0,
        avg_volume=avg_vol,
        current_price=float(hist["Close"].iloc[-1]),
        price_history=hist,
        eps=None,
        eps_growth_yoy=None,
        revenue_growth_yoy=None,
        pe_ratio=None,
        profit_margin=None,
        analyst_rating=None,
        analyst_target=None,
        news_headlines=[],
    )
