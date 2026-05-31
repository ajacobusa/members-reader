import pandas as pd
import yaml
from stock_dashboard.engine.backtest import (
    backtest_timings, select_best_timing, auto_tune,
)


def _ohlc(opens, closes):
    n = len(opens)
    return pd.DataFrame({
        "Open": opens, "High": [c * 1.01 for c in closes],
        "Low": [o * 0.99 for o in opens], "Close": closes,
        "Volume": [1_000_000] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="B"))


def test_backtest_timings_reports_all_strategies():
    ohlc = {"AAA": _ohlc([100, 101, 102, 103], [101, 102, 103, 104])}
    res = backtest_timings(ohlc)
    assert set(res.keys()) == {"A", "B", "C", "D"}
    for stats in res.values():
        assert "avg_return_pct" in stats and "win_rate" in stats


def test_select_best_timing_picks_highest_sharpe():
    res = {"A": {"sharpe": 0.5}, "B": {"sharpe": 1.2}, "C": {"sharpe": 0.9},
           "D": {"sharpe": -0.3}}
    assert select_best_timing(res) == "B"


def test_auto_tune_refuses_below_sample_guard(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("backtest:\n  min_sample_trades: 200\n  min_improvement_pct: 0.2\n")
    applied = auto_tune(str(cfg_file), best_timing="C", new_weights={},
                        sample_trades=50, improvement_pct=1.0,
                        min_sample_trades=200, min_improvement_pct=0.2)
    assert applied is False
    assert "preferred_timing" not in cfg_file.read_text()


def test_auto_tune_applies_when_guards_pass_and_backs_up(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("backtest:\n  preferred_timing: A\n")
    applied = auto_tune(str(cfg_file), best_timing="C", new_weights={},
                        sample_trades=500, improvement_pct=1.0,
                        min_sample_trades=200, min_improvement_pct=0.2)
    assert applied is True
    data = yaml.safe_load(cfg_file.read_text())
    assert data["backtest"]["preferred_timing"] == "C"
    assert any(p.name.startswith("config.bak.") for p in tmp_path.iterdir())
