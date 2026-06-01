import datetime
import logging
from typing import Optional, Callable
import numpy as np
import pandas as pd
from stock_dashboard.engine.config_loader import Config
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.scorer import score_stock, ScoreResult
from stock_dashboard.engine.statistics import build_profile
from stock_dashboard.engine.enrichment import rank_and_filter
from stock_dashboard.db.database import PickRecord

log = logging.getLogger(__name__)


def enrich_from_sources(stock, cfg) -> list[str]:
    """Augment a SURVIVOR stock with multi-source data. Returns sources used.
    No-op (no cost) when no API keys are configured."""
    keys = cfg.api_keys
    if not any((keys.get("newsapi"), keys.get("fmp"), keys.get("finnhub"))):
        return []
    from stock_dashboard.engine.sources.aggregator import aggregate
    from stock_dashboard.engine.cache import Cache
    perf = cfg.performance
    cache = Cache(perf.get("cache_dir", "cache"), perf.get("cache_ttl_hours", 18))
    agg = aggregate(stock.ticker, stock.company, keys, cache=cache)

    # merge headlines (dedup against existing)
    existing = set(stock.news_headlines)
    for h in agg.headlines:
        if h not in existing:
            stock.news_headlines.append(h)
            existing.add(h)
    if agg.news_sentiment is not None:
        stock.sentiment_score = agg.news_sentiment
    if agg.analyst_target is not None and stock.analyst_target is None:
        stock.analyst_target = agg.analyst_target

    have = {c.get("type") for c in stock.catalysts}
    # analyst upgrade from FMP grades
    if agg.recent_upgrade and "analyst_upgrade" not in have:
        stock.catalysts.append({"type": "analyst_upgrade", "magnitude": 1.0,
                                "strength": 0.8, "label": "Analyst Upgrade (FMP)"})
    # price target increase
    pt_min = cfg.catalysts.get("price_target_increase", {}).get("min_increase_pct", 10)
    if (agg.analyst_target and stock.current_price and
            "price_target_increase" not in have and
            agg.analyst_target >= stock.current_price * (1 + pt_min / 100.0)):
        upside = (agg.analyst_target / stock.current_price - 1) * 100
        stock.catalysts.append({"type": "price_target_increase",
                                "magnitude": round(upside, 1),
                                "strength": min(upside / 30, 1.0),
                                "label": f"PT +{upside:.0f}% upside (FMP)"})
    # earnings beat from FMP surprise
    eb_min = cfg.catalysts.get("earnings_beat", {}).get("min_beat_pct", 5)
    if (agg.earnings_surprise_pct is not None and
            agg.earnings_surprise_pct >= eb_min and "earnings_beat" not in have):
        stock.catalysts.append({"type": "earnings_beat",
                                "magnitude": agg.earnings_surprise_pct,
                                "strength": min(agg.earnings_surprise_pct / 30, 1.0),
                                "label": f"Earnings Beat +{agg.earnings_surprise_pct:.0f}% (FMP)"})
    return agg.sources_used


def gate1_quality(stock: StockData, cfg: Config) -> bool:
    qf = cfg.quality_filter
    if stock.market_cap < qf["min_market_cap_b"]:
        return False
    if stock.avg_volume < qf["min_avg_volume"]:
        return False
    if qf["require_profitable"] and (stock.eps is None or stock.eps <= 0):
        return False
    return True

def gate2_market(vix: float, spy_vs_50sma: float, fear_greed: int, cfg: Config) -> bool:
    mc = cfg.market_conditions
    if vix > mc["max_vix"]:
        return False
    if mc["require_above_50sma"] and spy_vs_50sma <= 0:
        return False
    if fear_greed < mc["min_fear_greed"]:
        return False
    return True

def gate3_catalyst(stock: StockData, cfg: Config, earnings_data: dict) -> bool:
    today = datetime.date.today()
    found = False
    cats = cfg.catalysts

    ec = cats.get("earnings_beat", {})
    if ec.get("enabled") and stock.ticker in earnings_data:
        ed = earnings_data[stock.ticker]
        try:
            report_date = datetime.date.fromisoformat(ed["date"])
        except (KeyError, ValueError):
            report_date = None
        if report_date and (today - report_date).days <= ec["lookback_days"]:
            actual = ed.get("eps_actual", 0) or 0
            estimate = ed.get("eps_estimate", 1) or 1
            if estimate != 0:
                beat_pct = (actual - estimate) / abs(estimate) * 100
                if beat_pct >= ec["min_beat_pct"]:
                    stock.catalysts.append({
                        "type": "earnings_beat",
                        "magnitude": round(beat_pct, 1),
                        "strength": min(beat_pct / 30, 1.0),
                        "label": f"Earnings Beat +{beat_pct:.1f}%",
                    })
                    found = True

    vc = cats.get("volume_breakout", {})
    if vc.get("enabled") and len(stock.price_history) >= 20:
        vol = stock.price_history["Volume"]
        avg_vol = vol.iloc[-20:].mean()
        if avg_vol > 0 and vol.iloc[-1] > avg_vol * vc["multiplier"]:
            ratio = vol.iloc[-1] / avg_vol
            stock.catalysts.append({
                "type": "volume_breakout",
                "magnitude": round(float(ratio), 2),
                "strength": min((ratio - 1) / 3, 1.0),
                "label": f"Volume {ratio:.1f}x Average",
            })
            found = True

    hc = cats.get("high_52w_breakout", {})
    if hc.get("enabled") and len(stock.price_history) >= 50:
        high_52w = stock.price_history["High"].max()
        if stock.current_price > float(high_52w):
            stock.catalysts.append({
                "type": "high_52w_breakout",
                "magnitude": stock.current_price,
                "strength": 0.8,
                "label": "52-Week High Breakout",
            })
            found = True

    ac = cats.get("analyst_upgrade", {})
    if ac.get("enabled") and stock.analyst_rating in ("strongBuy", "strong_buy", "buy"):
        any_upgrade_news = any(
            any(kw in h.lower() for kw in ("upgrade", "raises", "strong buy", "buy rating"))
            for h in stock.news_headlines
        )
        if any_upgrade_news:
            stock.catalysts.append({
                "type": "analyst_upgrade",
                "magnitude": 1.0,
                "strength": 0.9 if "strong" in (stock.analyst_rating or "") else 0.7,
                "label": f"Analyst {(stock.analyst_rating or '').title()} Rating",
            })
            found = True

    return found

def gate4_technical(stock: StockData, cfg: Config) -> bool:
    closes = stock.price_history["Close"]
    tg = cfg.technical_gates

    if len(closes) >= 15:
        delta = closes.diff().dropna()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        # Skip RSI gate when it cannot be computed (e.g. pure uptrend with zero losses)
        if not np.isnan(rsi_val) and not (tg["rsi_min"] <= rsi_val <= tg["rsi_max"]):
            return False

    if tg["require_above_20sma"] and len(closes) >= 20:
        sma20 = float(closes.rolling(20).mean().iloc[-1])
        if closes.iloc[-1] < sma20:
            return False
        extension = (closes.iloc[-1] - sma20) / sma20 * 100
        if extension > tg["max_extension_pct"]:
            return False

    if tg["require_macd_bullish"] and len(closes) >= 35:
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        if float((macd - signal).iloc[-1]) <= 0:
            return False

    return True

def build_narrative(stock: StockData, score: ScoreResult) -> str:
    parts = []
    for cat in stock.catalysts:
        parts.append(cat["label"])
    if stock.eps_growth_yoy and stock.eps_growth_yoy > 0.1:
        parts.append(f"EPS growth {stock.eps_growth_yoy*100:.0f}% YoY")
    if stock.revenue_growth_yoy and stock.revenue_growth_yoy > 0.08:
        parts.append(f"revenue growth {stock.revenue_growth_yoy*100:.0f}% YoY")
    if stock.analyst_rating in ("strongBuy", "strong_buy"):
        parts.append("analyst Strong Buy")
    if stock.profit_margin and stock.profit_margin > 0.20:
        parts.append(f"profit margin {stock.profit_margin*100:.0f}%")
    if stock.news_headlines:
        parts.append(stock.news_headlines[0])
    return " · ".join(parts) if parts else "Strong technical and fundamental setup."

def run_pipeline(
    tickers: list[str],
    cfg: Config,
    market_data: dict,
    earnings_data: dict,
    sector_pe_map: dict[str, float],
    marked_picks_count: int,
    fetch_fn: Optional[Callable] = None,
) -> tuple[list[PickRecord], bool]:
    from stock_dashboard.engine.fetcher import fetch_stock_data
    fetch = fetch_fn or fetch_stock_data

    vix = market_data.get("vix", 20.0)
    spy_vs_50sma = market_data.get("spy_vs_50sma", 0.02)
    fear_greed = market_data.get("fear_greed", 50)

    market_ok = gate2_market(vix, spy_vs_50sma, fear_greed, cfg)
    if not market_ok:
        log.warning("Market conditions unfavorable — pipeline aborted")
        return [], False

    scored: list[ScoreResult] = []
    stock_lookup: dict[str, StockData] = {}

    for ticker in tickers:
        stock = fetch(ticker)
        if stock is None:
            continue
        if not gate1_quality(stock, cfg):
            continue
        has_catalyst = gate3_catalyst(stock, cfg, earnings_data)
        if cfg.ranking.get("require_catalyst", True) and not has_catalyst:
            continue
        if not gate4_technical(stock, cfg):
            continue
        enrich_from_sources(stock, cfg)  # multi-source augmentation (survivors only)
        result = score_stock(stock, cfg, sector_pe_map, marked_picks_count)
        result.narrative = build_narrative(stock, result)
        result.catalysts = stock.catalysts
        scored.append(result)
        stock_lookup[ticker] = stock

    # Build (profile, PickRecord) pairs for survivors, then enrich + EV-rank + profit-gate
    today = datetime.date.today().isoformat()
    inputs = []
    factor_inputs = {}
    for result in scored:
        stock = stock_lookup[result.ticker]
        profile = build_profile(stock, cfg)
        rec = PickRecord(
            date=today, ticker=result.ticker, company=stock.company,
            price=float(stock.current_price),
            composite_score=result.composite, technical_score=result.technical,
            fundamental_score=result.fundamental, catalyst_score=result.catalyst_score,
            pattern_score=result.pattern_score, catalysts=result.catalysts,
            narrative=result.narrative, signals=result.signals,
        )
        inputs.append((profile, rec))
        factor_inputs[result.ticker] = {
            "relative_volume": float(result.signals.get("volume_ratio", 0.5)),
            "technical_momentum": float(result.signals.get("momentum_20d", 0.5)),
            "sector_strength": 0.5,
        }

    enriched = rank_and_filter(inputs, options_map={}, factor_inputs=factor_inputs, cfg=cfg)
    records = [e.pick for e in enriched][: cfg.scoring["top_n"]]
    return records, True
