"""Finnhub.io provider — recommendation trends, news, sentiment."""
from typing import Callable, Optional
from stock_dashboard.engine.sources.base import http_get_json

_BASE = "https://finnhub.io/api/v1"


def fetch_recommendation(ticker: str, api_key: str,
                         get_fn: Callable = http_get_json) -> Optional[str]:
    """Return a normalized consensus string (strong_buy/buy/hold/sell) or None."""
    if not api_key:
        return None
    data = get_fn(f"{_BASE}/stock/recommendation",
                  params={"symbol": ticker, "token": api_key})
    if not data or not isinstance(data, list) or not data:
        return None
    latest = data[0]  # most recent period first
    scores = {"strong_buy": latest.get("strongBuy", 0), "buy": latest.get("buy", 0),
              "hold": latest.get("hold", 0), "sell": latest.get("sell", 0),
              "strong_sell": latest.get("strongSell", 0)}
    return max(scores, key=scores.get) if any(scores.values()) else None


def fetch_news_sentiment(ticker: str, api_key: str,
                         get_fn: Callable = http_get_json) -> Optional[float]:
    """Return a bullishness score 0..1 or None."""
    if not api_key:
        return None
    data = get_fn(f"{_BASE}/news-sentiment",
                  params={"symbol": ticker, "token": api_key})
    if not data:
        return None
    s = data.get("sentiment") or {}
    val = s.get("bullishPercent")
    if val is None:
        val = data.get("companyNewsScore")
    return float(val) if val is not None else None


def fetch_company_news(ticker: str, api_key: str,
                       get_fn: Callable = http_get_json, limit: int = 10) -> list[str]:
    if not api_key:
        return []
    import datetime
    today = datetime.date.today()
    frm = (today - datetime.timedelta(days=7)).isoformat()
    data = get_fn(f"{_BASE}/company-news",
                  params={"symbol": ticker, "from": frm, "to": today.isoformat(),
                          "token": api_key})
    if not data or not isinstance(data, list):
        return []
    return [n["headline"] for n in data if n.get("headline")][:limit]
