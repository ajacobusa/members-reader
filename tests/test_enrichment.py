import pytest
from stock_dashboard.engine.enrichment import (
    expected_value_rank, kelly_size, conviction, passes_profit_gate, EnrichedPick,
)
from stock_dashboard.engine.config_loader import load_config


def test_kelly_size_half_kelly_and_capped(config_path):
    cfg = load_config(config_path)
    assert kelly_size(0.4, cfg) == pytest.approx(10.0)
    assert kelly_size(0.1, cfg) == pytest.approx(5.0)


def test_conviction_blend(config_path):
    cfg = load_config(config_path)
    assert conviction(0.8, 90.0, cfg) == pytest.approx(0.85)


def test_expected_value_rank_monotonic():
    a = expected_value_rank(expected_return_pct=2.0, prob_gain=0.6, conviction_score=0.8)
    b = expected_value_rank(expected_return_pct=1.0, prob_gain=0.6, conviction_score=0.8)
    assert a > b


def test_profit_gate_passes_strong_pick(config_path):
    cfg = load_config(config_path)
    assert passes_profit_gate(composite=85, expected_return_pct=2.0,
                              prob_gain=0.65, risk_reward=2.5, cfg=cfg) is True


def test_profit_gate_rejects_low_probability(config_path):
    cfg = load_config(config_path)
    assert passes_profit_gate(composite=85, expected_return_pct=2.0,
                              prob_gain=0.55, risk_reward=2.5, cfg=cfg) is False


def test_profit_gate_applies_cost_haircut(config_path):
    cfg = load_config(config_path)
    assert passes_profit_gate(composite=85, expected_return_pct=1.2,
                              prob_gain=0.65, risk_reward=2.5, cfg=cfg) is False
