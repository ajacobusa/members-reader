"""Merge multiple data-source providers into one normalized result.
Each provider is skipped when its key is absent (graceful degradation)."""
from dataclasses import dataclass, field, asdict
from typing import Optional
from stock_dashboard.engine.sources import newsapi, finnhub, fmp


@dataclass
class AggregatedData:
    headlines: list[str] = field(default_factory=list)
    analyst_target: Optional[float] = None
    recent_upgrade: bool = False
    news_sentiment: Optional[float] = None
    earnings_surprise_pct: Optional[float] = None
    sources_used: list[str] = field(default_factory=list)


def aggregate(ticker: str, company: str, api_keys: dict,
              headline_limit: int = 12, cache=None) -> AggregatedData:
    if cache is not None:
        cached = cache.get(ticker, "aggregate")
        if cached is not None:
            return AggregatedData(**cached)

    nk = api_keys.get("newsapi", "") or ""
    fk = api_keys.get("fmp", "") or ""
    hk = api_keys.get("finnhub", "") or ""

    headlines: list[str] = []
    sources: list[str] = []

    if nk:
        h = newsapi.fetch_headlines(ticker, company, nk)
        if h:
            headlines += h
        sources.append("newsapi")
    if hk:
        h = finnhub.fetch_company_news(ticker, hk)
        if h:
            headlines += h
        sources.append("finnhub")
    if fk:
        h = fmp.fetch_stock_news(ticker, fk)
        if h:
            headlines += h
        sources.append("fmp")

    # de-dup preserving order
    seen = set()
    deduped = []
    for t in headlines:
        if t not in seen:
            seen.add(t)
            deduped.append(t)

    analyst_target = fmp.fetch_price_target(ticker, fk) if fk else None
    recent_upgrade = fmp.fetch_recent_upgrade(ticker, fk) if fk else False
    surprise = fmp.fetch_latest_earnings_surprise_pct(ticker, fk) if fk else None
    sentiment = finnhub.fetch_news_sentiment(ticker, hk) if hk else None

    result = AggregatedData(
        headlines=deduped[:headline_limit], analyst_target=analyst_target,
        recent_upgrade=recent_upgrade, news_sentiment=sentiment,
        earnings_surprise_pct=surprise, sources_used=sources,
    )

    if cache is not None:
        try:
            cache.set(ticker, "aggregate", asdict(result))
        except Exception:
            pass
    return result
