"""NewsAPI.org provider — headlines restricted to financial outlets for relevance."""
from typing import Callable
from stock_dashboard.engine.sources.base import http_get_json

# Top financial outlets available through NewsAPI's index
_FINANCIAL_DOMAINS = ",".join([
    "reuters.com", "cnbc.com", "marketwatch.com", "finance.yahoo.com",
    "seekingalpha.com", "fool.com", "investing.com", "benzinga.com",
    "businessinsider.com", "forbes.com", "thestreet.com", "barrons.com",
])

_CONTEXT = "(stock OR shares OR earnings OR analyst OR guidance OR upgrade OR market)"


def fetch_headlines(ticker: str, company: str, api_key: str,
                    get_fn: Callable = http_get_json, limit: int = 10) -> list[str]:
    if not api_key:
        return []
    subject = f'"{company}" OR {ticker}' if company else ticker
    query = f"({subject}) AND {_CONTEXT}"
    data = get_fn("https://newsapi.org/v2/everything",
                  params={"q": query, "apiKey": api_key, "language": "en",
                          "domains": _FINANCIAL_DOMAINS, "searchIn": "title,description",
                          "sortBy": "publishedAt", "pageSize": limit})
    if not data or data.get("status") != "ok":
        return []
    return [a["title"] for a in data.get("articles", []) if a.get("title")][:limit]
