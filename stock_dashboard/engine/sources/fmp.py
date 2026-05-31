"""Financial Modeling Prep provider — price targets, analyst grades, earnings surprises, news."""
from typing import Callable, Optional
from stock_dashboard.engine.sources.base import http_get_json

_V3 = "https://financialmodelingprep.com/api/v3"
_V4 = "https://financialmodelingprep.com/api/v4"


def fetch_price_target(ticker: str, api_key: str,
                       get_fn: Callable = http_get_json) -> Optional[float]:
    if not api_key:
        return None
    data = get_fn(f"{_V4}/price-target-consensus",
                  params={"symbol": ticker, "apikey": api_key})
    if not data:
        return None
    row = data[0] if isinstance(data, list) and data else data
    val = row.get("targetConsensus") if isinstance(row, dict) else None
    return float(val) if val is not None else None


def fetch_recent_upgrade(ticker: str, api_key: str,
                         get_fn: Callable = http_get_json, lookback: int = 5) -> bool:
    """True if any recent analyst action was an upgrade."""
    if not api_key:
        return False
    data = get_fn(f"{_V3}/grade/{ticker}", params={"apikey": api_key})
    if not data or not isinstance(data, list):
        return False
    for row in data[:lookback]:
        action = (row.get("newGrade", "") or "").lower()
        prev = (row.get("previousGrade", "") or "").lower()
        # heuristic: moved into a buy-ish grade
        if action in ("buy", "strong buy", "outperform", "overweight") and action != prev:
            return True
    return False


def fetch_latest_earnings_surprise_pct(ticker: str, api_key: str,
                                       get_fn: Callable = http_get_json) -> Optional[float]:
    if not api_key:
        return None
    data = get_fn(f"{_V3}/earnings-surprises/{ticker}", params={"apikey": api_key})
    if not data or not isinstance(data, list) or not data:
        return None
    row = data[0]
    actual = row.get("actualEarningResult")
    est = row.get("estimatedEarning")
    if actual is None or est in (None, 0):
        return None
    return round((actual - est) / abs(est) * 100.0, 2)


def fetch_stock_news(ticker: str, api_key: str,
                     get_fn: Callable = http_get_json, limit: int = 10) -> list[str]:
    if not api_key:
        return []
    data = get_fn(f"{_V3}/stock_news",
                  params={"tickers": ticker, "limit": limit, "apikey": api_key})
    if not data or not isinstance(data, list):
        return []
    return [n["title"] for n in data if n.get("title")][:limit]
