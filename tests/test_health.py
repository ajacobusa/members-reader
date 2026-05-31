import math
from stock_dashboard.health import sanity_check_pick, HealthReport, is_degraded
from stock_dashboard.db.database import PickRecord
from stock_dashboard.engine.config_loader import load_config


def _rec(**kw):
    base = dict(date="2026-05-31", ticker="X", company="X", price=100.0,
                composite_score=85, technical_score=80, fundamental_score=80,
                catalyst_score=80, pattern_score=0, catalysts=[], narrative="",
                signals={}, expected_return_pct=1.5, prob_gain=0.6,
                ci_low_pct=-2.0, ci_high_pct=5.0, suggested_size_pct=4.0)
    base.update(kw)
    return PickRecord(**base)


def test_sanity_check_passes_clean_pick():
    assert sanity_check_pick(_rec()) == []

def test_sanity_check_flags_nan():
    assert sanity_check_pick(_rec(expected_return_pct=float("nan")))

def test_sanity_check_flags_bad_probability():
    assert sanity_check_pick(_rec(prob_gain=1.4))

def test_sanity_check_flags_ci_ordering():
    assert sanity_check_pick(_rec(ci_low_pct=5.0, ci_high_pct=-5.0))

def test_sanity_check_flags_nonpositive_price():
    assert sanity_check_pick(_rec(price=0.0))

def test_is_degraded_low_fetch_rate(config_path):
    cfg = load_config(config_path)
    report = HealthReport(total_tickers=100, fetched=50, options_covered=20,
                          earnings_covered=10, gate_survivors=5, sanity_failures=0,
                          market_data_ok=True)
    assert is_degraded(report, cfg) is True

def test_is_degraded_false_when_healthy(config_path):
    cfg = load_config(config_path)
    report = HealthReport(total_tickers=100, fetched=95, options_covered=70,
                          earnings_covered=60, gate_survivors=8, sanity_failures=0,
                          market_data_ok=True)
    assert is_degraded(report, cfg) is False
