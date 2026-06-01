"""Financial Modeling Prep provider (STABLE API). Free tier: grades, consensus,
price-target-summary, earnings. News is paid (returns [] gracefully)."""
from typing import Callable, Optional
from stock_dashboard.engine.sources.base import http_get_json

_BASE = "https://financialmodelingprep.com/stable"
_BUYISH = ("buy", "strong buy", "outperform", "overweight", "accumulate", "add")


def fetch_price_target(ticker: str, api_key: str,
                       get_fn: Callable = http_get_json) -> Optional[float]:
    if not api_key:
        return None
    data = get_fn(f"{_BASE}/price-target-summary",
                  params={"symbol": ticker, "apikey": api_key})
    if not data:
        return None
    row = data[0] if isinstance(data, list) and data else data
    if not isinstance(row, dict):
        return None
    val = row.get("lastMonthAvgPriceTarget") or row.get("lastQuarterAvgPriceTarget")
    return float(val) if val else None


def fetch_recent_upgrade(ticker: str, api_key: str,
                         get_fn: Callable = http_get_json, lookback: int = 5) -> bool:
    if not api_key:
        return False
    data = get_fn(f"{_BASE}/grades", params={"symbol": ticker, "apikey": api_key})
    if not data or not isinstance(data, list):
        return False
    for row in data[:lookback]:
        new = (row.get("newGrade", "") or "").lower()
        prev = (row.get("previousGrade", "") or "").lower()
        if new in _BUYISH and new != prev:
            return True
    return False


def fetch_latest_earnings_surprise_pct(ticker: str, api_key: str,
                                       get_fn: Callable = http_get_json) -> Optional[float]:
    if not api_key:
        return None
    data = get_fn(f"{_BASE}/earnings", params={"symbol": ticker, "apikey": api_key})
    if not data or not isinstance(data, list):
        return None
    for row in data:  # newest first; skip future rows (epsActual is None)
        actual = row.get("epsActual")
        est = row.get("epsEstimated")
        if actual is not None and est not in (None, 0):
            return round((actual - est) / abs(est) * 100.0, 2)
    return None


def fetch_consensus(ticker: str, api_key: str,
                    get_fn: Callable = http_get_json) -> Optional[str]:
    if not api_key:
        return None
    data = get_fn(f"{_BASE}/grades-consensus",
                  params={"symbol": ticker, "apikey": api_key})
    if not data:
        return None
    row = data[0] if isinstance(data, list) and data else data
    c = row.get("consensus") if isinstance(row, dict) else None
    return c.lower().replace(" ", "_") if c else None


def fetch_stock_news(ticker: str, api_key: str,
                     get_fn: Callable = http_get_json, limit: int = 10) -> list[str]:
    """News is paid-only on the free tier; returns [] gracefully there."""
    if not api_key:
        return []
    data = get_fn(f"{_BASE}/news/stock-latest",
                  params={"symbols": ticker, "limit": limit, "apikey": api_key})
    if not data or not isinstance(data, list):
        return []
    return [n["title"] for n in data if n.get("title")][:limit]
