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


from stock_dashboard.engine.enrichment import factor_score, rank_and_filter
from stock_dashboard.engine.statistics import ProbabilityProfile


def _profile(ev=2.0, pg=0.65, rr=2.5, kelly=0.3):
    return ProbabilityProfile(
        ticker="TST", earnings_beat_rate=0.75, earnings_avg_move_pct=4.0,
        earnings_median_move_pct=3.0, earnings_sample_size=8,
        eps_revision_30d_pct=12.0, eps_revision_60d_pct=8.0, pt_change_30d_pct=5.0,
        prob_gain=pg, avg_gain_pct=4.0, avg_loss_pct=1.6, expected_return_pct=ev,
        return_std_pct=2.0, ci_low_pct=ev - 3, ci_high_pct=ev + 3,
        risk_reward=rr, risk_score=20.0, kelly_fraction=kelly, sample_size=120,
    )


def test_factor_score_in_unit_range(config_path):
    cfg = load_config(config_path)
    fs = factor_score(profile=_profile(), options=None,
                      relative_volume=0.8, technical_momentum=0.7,
                      sector_strength=0.6, cfg=cfg)
    assert 0.0 <= fs <= 1.0


def test_rank_and_filter_orders_by_ev_and_drops_failures(config_path):
    cfg = load_config(config_path)
    from stock_dashboard.db.database import PickRecord
    def mk(ticker, ev, pg, comp):
        prof = _profile(ev=ev, pg=pg)
        rec = PickRecord(date="2026-05-31", ticker=ticker, company=ticker,
                         price=100.0, composite_score=comp, technical_score=80,
                         fundamental_score=80, catalyst_score=80, pattern_score=0,
                         catalysts=[], narrative="", signals={})
        return prof, rec
    inputs = [mk("LOW", ev=1.5, pg=0.65, comp=85),
              mk("HIGH", ev=3.0, pg=0.65, comp=85),
              mk("FAIL", ev=2.0, pg=0.50, comp=85)]
    enriched = rank_and_filter(inputs, options_map={}, factor_inputs={}, cfg=cfg)
    tickers = [e.pick.ticker for e in enriched]
    assert tickers == ["HIGH", "LOW"]


def test_factor_score_renormalizes_over_present_factors(config_path):
    cfg = load_config(config_path)
    # disable everything except relative_volume and technical_momentum
    for name, spec in cfg.factor_weights.items():
        spec["enabled"] = name in ("relative_volume", "technical_momentum")
    # weights: relative_volume 0.10, technical_momentum 0.10 -> renormalize to 0.5/0.5
    fs = factor_score(profile=_profile(), options=None,
                      relative_volume=1.0, technical_momentum=0.0,
                      sector_strength=0.5, cfg=cfg)
    # 0.5*1.0 + 0.5*0.0 = 0.5
    assert fs == pytest.approx(0.5, abs=1e-9)


def test_options_flow_low_put_call_scores_higher(config_path):
    from stock_dashboard.engine.options import OptionsSignal
    cfg = load_config(config_path)
    bullish = OptionsSignal("T", 0.4, 0.4, True, False, 100.0, 50.0, True)   # low P/C
    bearish = OptionsSignal("T", 0.4, 1.5, False, True, 100.0, -50.0, True)  # high P/C
    hi = factor_score(_profile(), bullish, 0.5, 0.5, 0.5, cfg)
    lo = factor_score(_profile(), bearish, 0.5, 0.5, 0.5, cfg)
    assert hi > lo


def test_profit_gate_disabled_passes_everything(config_path):
    cfg = load_config(config_path)
    cfg.probability_filter["enabled"] = False
    assert passes_profit_gate(composite=0, expected_return_pct=-5.0,
                              prob_gain=0.0, risk_reward=0.0, cfg=cfg) is True
