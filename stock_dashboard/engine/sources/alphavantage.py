"""Alpha Vantage provider — news sentiment (free tier ~25 req/day; use with cache)."""
from typing import Callable, Optional
from stock_dashboard.engine.sources.base import http_get_json

_BASE = "https://www.alphavantage.co/query"


def _feed(ticker: str, api_key: str, get_fn: Callable, limit: int):
    data = get_fn(_BASE, params={"function": "NEWS_SENTIMENT", "tickers": ticker,
                                 "apikey": api_key, "limit": limit})
    if not isinstance(data, dict):
        return None
    return data.get("feed")  # None when rate-limited (Note/Information payloads)


def fetch_sentiment(ticker: str, api_key: str,
                    get_fn: Callable = http_get_json) -> Optional[float]:
    """Return bullishness 0..1 (from AV ticker_sentiment_score -1..1) or None."""
    if not api_key:
        return None
    feed = _feed(ticker, api_key, get_fn, 50)
    if not feed:
        return None
    scores = []
    for item in feed:
        for ts in item.get("ticker_sentiment", []):
            if ts.get("ticker") == ticker:
                try:
                    scores.append(float(ts.get("ticker_sentiment_score")))
                except (TypeError, ValueError):
                    pass
    if not scores:
        return None
    avg = sum(scores) / len(scores)            # -1..1
    return round((avg + 1) / 2, 4)             # 0..1


def fetch_headlines(ticker: str, api_key: str,
                    get_fn: Callable = http_get_json, limit: int = 10) -> list[str]:
    if not api_key:
        return []
    feed = _feed(ticker, api_key, get_fn, limit)
    if not feed:
        return []
    return [it["title"] for it in feed if it.get("title")][:limit]
