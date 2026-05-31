from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import Config


@dataclass
class ProbabilityProfile:
    ticker: str
    earnings_beat_rate: Optional[float]
    earnings_avg_move_pct: Optional[float]
    earnings_median_move_pct: Optional[float]
    earnings_sample_size: int
    eps_revision_30d_pct: Optional[float]
    eps_revision_60d_pct: Optional[float]
    pt_change_30d_pct: Optional[float]
    prob_gain: float
    avg_gain_pct: float
    avg_loss_pct: float
    expected_return_pct: float
    return_std_pct: float
    ci_low_pct: float
    ci_high_pct: float
    risk_reward: float
    risk_score: float
    kelly_fraction: float
    sample_size: int


def move_distribution(returns: pd.Series) -> dict:
    """returns: daily simple returns (fraction). All outputs in PERCENT."""
    r = pd.Series(returns).dropna()
    if len(r) == 0:
        return {"prob_gain": 0.0, "avg_gain_pct": 0.0, "avg_loss_pct": 0.0,
                "expected_return_pct": 0.0, "return_std_pct": 0.0, "n": 0}
    pct = r * 100.0
    gains = pct[pct > 0]
    losses = pct[pct < 0]
    prob_gain = float(len(gains) / len(pct))
    avg_gain = float(gains.mean()) if len(gains) else 0.0
    avg_loss = float(-losses.mean()) if len(losses) else 0.0
    ev = prob_gain * avg_gain - (1 - prob_gain) * avg_loss
    return {"prob_gain": prob_gain, "avg_gain_pct": avg_gain,
            "avg_loss_pct": avg_loss, "expected_return_pct": float(ev),
            "return_std_pct": float(pct.std(ddof=0)) if len(pct) > 1 else 0.0,
            "n": int(len(pct))}


def kelly_fraction(prob_gain: float, avg_gain_pct: float, avg_loss_pct: float) -> float:
    if avg_loss_pct <= 0:
        return 0.0
    b = avg_gain_pct / avg_loss_pct
    f = (prob_gain * b - (1 - prob_gain)) / b
    return float(max(0.0, f))


def confidence_interval(expected_pct: float, std_pct: float, k: float) -> tuple[float, float]:
    return (expected_pct - k * std_pct, expected_pct + k * std_pct)


def _earnings_stats(stock: StockData, quarters: int) -> dict:
    """Beat rate + post-earnings move from optional stock.earnings_history.
    Returns neutral values when data is absent (free-data limitation)."""
    eps_hist = getattr(stock, "earnings_history", None)
    if not eps_hist:
        return {"beat_rate": None, "avg_move": None, "median_move": None, "n": 0}
    beats = [1 for e in eps_hist if e.get("actual") is not None and
             e.get("estimate") not in (None, 0) and e["actual"] > e["estimate"]]
    moves = [e["move_pct"] for e in eps_hist if e.get("move_pct") is not None]
    n = len(eps_hist[:quarters])
    return {
        "beat_rate": (len(beats) / n) if n else None,
        "avg_move": float(np.mean(moves)) if moves else None,
        "median_move": float(np.median(moves)) if moves else None,
        "n": n,
    }


def _revision_velocity(stock: StockData) -> dict:
    trend = getattr(stock, "eps_trend", None) or {}
    def pct(now, then):
        if now is None or then in (None, 0):
            return None
        return (now - then) / abs(then) * 100.0
    return {
        "rev_30d": pct(trend.get("current"), trend.get("30d_ago")),
        "rev_60d": pct(trend.get("current"), trend.get("60d_ago")),
        "pt_30d": pct(trend.get("pt_current"), trend.get("pt_30d_ago")),
    }


def build_profile(stock: StockData, cfg: Config) -> ProbabilityProfile:
    s = cfg.statistics
    closes = stock.price_history["Close"]
    rets = closes.pct_change().dropna().iloc[-int(s["return_lookback_days"]):]
    d = move_distribution(rets)
    k = float(s["ci_sigma_multiplier"])
    ci_low, ci_high = confidence_interval(d["expected_return_pct"], d["return_std_pct"], k)
    rr = (d["avg_gain_pct"] / d["avg_loss_pct"]) if d["avg_loss_pct"] > 0 else 0.0
    kelly = kelly_fraction(d["prob_gain"], d["avg_gain_pct"], d["avg_loss_pct"])
    risk = float(np.clip(d["return_std_pct"] * 10 - rr * 5, 0, 100))
    es = _earnings_stats(stock, int(s["earnings_lookback_quarters"]))
    rv = _revision_velocity(stock)
    return ProbabilityProfile(
        ticker=stock.ticker,
        earnings_beat_rate=es["beat_rate"], earnings_avg_move_pct=es["avg_move"],
        earnings_median_move_pct=es["median_move"], earnings_sample_size=es["n"],
        eps_revision_30d_pct=rv["rev_30d"], eps_revision_60d_pct=rv["rev_60d"],
        pt_change_30d_pct=rv["pt_30d"],
        prob_gain=d["prob_gain"], avg_gain_pct=d["avg_gain_pct"],
        avg_loss_pct=d["avg_loss_pct"], expected_return_pct=d["expected_return_pct"],
        return_std_pct=d["return_std_pct"], ci_low_pct=ci_low, ci_high_pct=ci_high,
        risk_reward=rr, risk_score=risk, kelly_fraction=kelly, sample_size=d["n"],
    )
