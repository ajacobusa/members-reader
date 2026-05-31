#!/usr/bin/env python3
"""Weekly unattended backtest + guarded auto-tune. Task Scheduler entry point."""
import datetime
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))
logging.basicConfig(filename=ROOT / "logs" / "backtest.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    from stock_dashboard.engine.config_loader import load_config
    from stock_dashboard.engine.universe import get_universe
    from stock_dashboard.engine.backtest import (
        backtest_timings, select_best_timing, auto_tune,
    )
    cfg = load_config(ROOT / "config.yaml")
    tickers = get_universe(cfg)[:100]  # bound cost; extend as desired

    import yfinance as yf
    years = int(cfg.backtest["years"])
    data = yf.download(tickers, period=f"{years}y", group_by="ticker",
                       auto_adjust=False, threads=True)
    ohlc = {}
    for t in tickers:
        try:
            df = data[t].dropna()
            if not df.empty:
                ohlc[t] = df
        except Exception:
            continue

    results = backtest_timings(ohlc)
    best = select_best_timing(results)
    total_trades = sum(s["n"] for s in results.values())
    baseline = results.get(cfg.backtest.get("preferred_timing", "C"), {}).get("sharpe", 0)
    improvement = results[best]["sharpe"] - baseline

    log.info("Backtest results: %s; best=%s", results, best)
    if cfg.backtest.get("auto_tune"):
        applied = auto_tune(
            str(ROOT / "config.yaml"), best_timing=best, new_weights={},
            sample_trades=total_trades, improvement_pct=improvement,
            min_sample_trades=int(cfg.backtest["min_sample_trades"]),
            min_improvement_pct=float(cfg.backtest["min_improvement_pct"]),
        )
        log.info("auto_tune applied=%s", applied)


if __name__ == "__main__":
    main()
