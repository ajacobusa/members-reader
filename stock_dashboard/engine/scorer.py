from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import Config

@dataclass
class ScoreResult:
    ticker: str
    composite: float
    technical: float
    fundamental: float
    catalyst_score: float
    pattern_score: float
    signals: dict
    narrative: str = ""
    catalysts: list = field(default_factory=list)

def _rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

def _rsi_score(rsi_val: float) -> float:
    if 50 <= rsi_val <= 65:
        return 1.0
    if 40 <= rsi_val < 50 or 65 < rsi_val <= 70:
        return 0.6
    return 0.2

def _macd_bullish(closes: pd.Series) -> tuple[bool, float]:
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    bullish = bool(hist.iloc[-1] > 0)
    strength = min(abs(float(hist.iloc[-1])) / (closes.iloc[-1] * 0.01 + 1e-9), 1.0)
    return bullish, strength

def _momentum_20d(closes: pd.Series) -> float:
    if len(closes) < 20:
        return 0.5
    mom = (closes.iloc[-1] - closes.iloc[-20]) / closes.iloc[-20]
    return float(np.clip((mom + 0.20) / 0.40, 0, 1))

def _volume_ratio(volumes: pd.Series) -> float:
    if len(volumes) < 20:
        return 0.5
    avg = volumes.iloc[-20:].mean()
    ratio = volumes.iloc[-1] / avg if avg > 0 else 1.0
    return float(np.clip((ratio - 0.5) / 3.0, 0, 1))

def _sma_crossover(closes: pd.Series) -> float:
    if len(closes) < 50:
        return 0.5
    sma20 = closes.rolling(20).mean().iloc[-1]
    sma50 = closes.rolling(50).mean().iloc[-1]
    if sma20 > sma50:
        return min((sma20 - sma50) / sma50 * 10, 1.0)
    return 0.0

def _eps_growth_score(growth: Optional[float]) -> float:
    if growth is None:
        return 0.5
    return float(np.clip((growth + 0.1) / 0.6, 0, 1))

def _revenue_growth_score(growth: Optional[float]) -> float:
    if growth is None:
        return 0.5
    return float(np.clip((growth + 0.05) / 0.45, 0, 1))

def _pe_vs_sector_score(pe: Optional[float], sector_pe: float) -> float:
    if pe is None or sector_pe <= 0:
        return 0.5
    ratio = pe / sector_pe
    if ratio <= 0.8:
        return 1.0
    if ratio <= 1.0:
        return 0.7
    if ratio <= 1.3:
        return 0.4
    return 0.1

def _analyst_score(rating: Optional[str]) -> float:
    mapping = {
        "strongbuy": 1.0, "strong_buy": 1.0,
        "buy": 0.8, "outperform": 0.75, "overweight": 0.75,
        "hold": 0.4, "neutral": 0.4, "marketperform": 0.4,
        "underperform": 0.1, "sell": 0.0, "underweight": 0.0,
    }
    return mapping.get((rating or "").lower().replace(" ", ""), 0.5)

def _profit_margin_score(margin: Optional[float]) -> float:
    if margin is None:
        return 0.5
    return float(np.clip(margin / 0.35, 0, 1))

def score_stock(stock: StockData, cfg: Config,
                sector_pe_map: dict[str, float],
                marked_picks_count: int) -> ScoreResult:
    closes = stock.price_history["Close"]
    volumes = stock.price_history["Volume"]
    sig = cfg.signals

    rsi_val = _rsi(closes)
    macd_bull, macd_strength = _macd_bullish(closes)

    tech_signals = {
        "rsi": _rsi_score(rsi_val) if sig.get("rsi", {}).get("enabled") else 0.5,
        "macd_bullish": (0.5 + macd_strength * 0.5) if (macd_bull and sig.get("macd", {}).get("enabled")) else 0.2,
        "momentum_20d": _momentum_20d(closes) if sig.get("momentum_20d", {}).get("enabled") else 0.5,
        "volume_ratio": _volume_ratio(volumes) if sig.get("volume_ratio", {}).get("enabled") else 0.5,
        "sma_crossover": _sma_crossover(closes) if sig.get("sma_crossover", {}).get("enabled") else 0.5,
    }
    sector_pe = sector_pe_map.get(stock.sector, 25.0)
    fund_signals = {
        "eps_growth": _eps_growth_score(stock.eps_growth_yoy) if sig.get("eps_growth", {}).get("enabled") else 0.5,
        "revenue_growth": _revenue_growth_score(stock.revenue_growth_yoy) if sig.get("revenue_growth", {}).get("enabled") else 0.5,
        "pe_vs_sector": _pe_vs_sector_score(stock.pe_ratio, sector_pe) if sig.get("pe_vs_sector", {}).get("enabled") else 0.5,
        "analyst_consensus": _analyst_score(stock.analyst_rating) if sig.get("analyst_consensus", {}).get("enabled") else 0.5,
        "profit_margin": _profit_margin_score(stock.profit_margin) if sig.get("profit_margin", {}).get("enabled") else 0.5,
    }

    tech_score = float(np.mean(list(tech_signals.values()))) * 100
    fund_score = float(np.mean(list(fund_signals.values()))) * 100

    catalyst_raw = float(np.mean([c.get("strength", 0.5) for c in stock.catalysts])) if stock.catalysts else 0.0
    catalyst_score = catalyst_raw * 100
    pattern_score = 0.0

    s = cfg.scoring
    tw = s["technical_weight"]
    fw = s["fundamental_weight"]
    cw = s["catalyst_weight"]
    pw = s["pattern_weight"] if marked_picks_count >= 10 else 0.0
    if pw == 0.0:
        extra = s["pattern_weight"] / 2
        tw += extra
        fw += extra

    composite = (tech_score * tw + fund_score * fw + catalyst_score * cw + pattern_score * pw)

    all_signals = {"rsi": round(rsi_val, 1), "macd_bullish": macd_bull,
                   **tech_signals, **fund_signals}

    return ScoreResult(
        ticker=stock.ticker,
        composite=round(composite, 1),
        technical=round(tech_score, 1),
        fundamental=round(fund_score, 1),
        catalyst_score=round(catalyst_score, 1),
        pattern_score=round(pattern_score, 1),
        signals=all_signals,
        catalysts=stock.catalysts,
    )
