import logging
import shutil
import time
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

log = logging.getLogger(__name__)


def _stats(returns_pct: np.ndarray) -> dict:
    if returns_pct.size == 0:
        return {"avg_return_pct": 0.0, "win_rate": 0.0, "sharpe": 0.0,
                "max_drawdown_pct": 0.0, "n": 0}
    avg = float(returns_pct.mean())
    win = float((returns_pct > 0).mean())
    std = float(returns_pct.std(ddof=0))
    sharpe = float(avg / std) if std > 0 else 0.0
    curve = np.cumsum(returns_pct)
    peak = np.maximum.accumulate(curve)
    dd = float((curve - peak).min())
    return {"avg_return_pct": avg, "win_rate": win, "sharpe": sharpe,
            "max_drawdown_pct": dd, "n": int(returns_pct.size)}


def backtest_timings(ohlc: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """Compare four entry/exit timings across all tickers' daily bars.
    A: open->next open  B: close->next close  C: close->next open  D: open->close
    """
    buckets = {"A": [], "B": [], "C": [], "D": []}
    for df in ohlc.values():
        o, c = df["Open"].to_numpy(), df["Close"].to_numpy()
        if len(o) < 2:
            continue
        buckets["A"].append((o[1:] - o[:-1]) / o[:-1] * 100)
        buckets["B"].append((c[1:] - c[:-1]) / c[:-1] * 100)
        buckets["C"].append((o[1:] - c[:-1]) / c[:-1] * 100)
        buckets["D"].append((c - o) / o * 100)
    return {k: _stats(np.concatenate(v) if v else np.array([]))
            for k, v in buckets.items()}


def select_best_timing(results: dict[str, dict]) -> str:
    return max(results, key=lambda k: results[k]["sharpe"])


def auto_tune(cfg_path: str, best_timing: str, new_weights: dict,
              sample_trades: int, improvement_pct: float,
              min_sample_trades: int, min_improvement_pct: float) -> bool:
    """Guarded: apply best_timing + new_weights to config only if guards pass.
    Backs up config first. Returns True if applied."""
    if sample_trades < min_sample_trades or improvement_pct < min_improvement_pct:
        log.info("auto_tune skipped: guards not met (n=%s, impr=%.3f)",
                 sample_trades, improvement_pct)
        return False
    src = Path(cfg_path)
    backup = src.parent / f"config.bak.{int(time.time())}.yaml"
    shutil.copyfile(src, backup)
    data = yaml.safe_load(src.read_text()) or {}
    data.setdefault("backtest", {})["preferred_timing"] = best_timing
    if new_weights:
        data["factor_weights"] = new_weights
    src.write_text(yaml.dump(data, default_flow_style=False))
    log.info("auto_tune applied timing=%s; backup at %s", best_timing, backup.name)
    return True
