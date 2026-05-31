"""NewsAPI.org provider — aggregated headlines from 80k+ outlets."""
from typing import Callable, Optional
from stock_dashboard.engine.sources.base import http_get_json


def fetch_headlines(ticker: str, company: str, api_key: str,
                    get_fn: Callable = http_get_json, limit: int = 10) -> list[str]:
    if not api_key:
        return []
    query = f'"{company}" OR {ticker}' if company else ticker
    data = get_fn("https://newsapi.org/v2/everything",
                  params={"q": query, "apiKey": api_key, "language": "en",
                          "sortBy": "publishedAt", "pageSize": limit})
    if not data or data.get("status") != "ok":
        return []
    return [a["title"] for a in data.get("articles", []) if a.get("title")][:limit]
