from dataclasses import dataclass
from typing import Optional
import json
import numpy as np
from stock_dashboard.engine.config_loader import Config
from stock_dashboard.engine.statistics import ProbabilityProfile
from stock_dashboard.engine.options import OptionsSignal
from stock_dashboard.db.database import PickRecord


@dataclass
class EnrichedPick:
    pick: PickRecord
    profile: ProbabilityProfile
    options: Optional[OptionsSignal]
    ev_rank: float
    suggested_size_pct: float
    passes_profit_gate: bool


def kelly_size(kelly_fraction: float, cfg: Config) -> float:
    sized = kelly_fraction * float(cfg.sizing["kelly_multiplier"]) * 100.0
    return float(np.clip(sized, 0.0, float(cfg.sizing["max_position_pct"])))


def conviction(factor_score: float, composite_0_100: float, cfg: Config) -> float:
    blend = float(cfg.enrichment["conviction_blend"])
    return blend * factor_score + (1 - blend) * (composite_0_100 / 100.0)


def expected_value_rank(expected_return_pct: float, prob_gain: float,
                        conviction_score: float) -> float:
    return float(expected_return_pct * prob_gain * conviction_score)


def passes_profit_gate(composite: float, expected_return_pct: float,
                       prob_gain: float, risk_reward: float, cfg: Config) -> bool:
    pf = cfg.probability_filter
    if not pf.get("enabled", True):
        return True
    ev_net = expected_return_pct - float(pf["cost_slippage_haircut_pct"])
    return (
        composite >= pf["min_composite_score"]
        and ev_net >= pf["min_expected_return_pct"]
        and prob_gain >= pf["min_probability_gain"]
        and risk_reward >= pf["min_risk_reward"]
    )


def _norm(value: Optional[float], lo: float, hi: float) -> float:
    if value is None:
        return 0.5
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def factor_score(profile: ProbabilityProfile, options: Optional[OptionsSignal],
                 relative_volume: float, technical_momentum: float,
                 sector_strength: float, cfg: Config) -> float:
    """Weighted blend (per cfg.factor_weights) of normalized factors; weights
    renormalize over factors that are present."""
    fw = cfg.factor_weights
    parts: list[tuple[float, float]] = []

    def add(name: str, value: Optional[float]):
        spec = fw.get(name, {})
        if spec.get("enabled") and value is not None:
            parts.append((float(spec["weight"]), float(value)))

    add("earnings_surprise", _norm(profile.earnings_beat_rate, 0.4, 0.9)
        if profile.earnings_beat_rate is not None else None)
    add("analyst_revision", _norm(profile.eps_revision_30d_pct, -10.0, 20.0))
    add("options_flow", None if options is None or not options.available
        else _norm(options.put_call_ratio, 1.5, 0.4))
    add("relative_volume", relative_volume)
    add("technical_momentum", technical_momentum)
    add("sector_strength", sector_strength)

    if not parts:
        return 0.5
    total_w = sum(w for w, _ in parts)
    return float(sum(w * v for w, v in parts) / total_w) if total_w else 0.5


def rank_and_filter(inputs: list[tuple], options_map: dict, factor_inputs: dict,
                    cfg: Config) -> list[EnrichedPick]:
    """inputs: list of (ProbabilityProfile, PickRecord).
    options_map: ticker -> OptionsSignal. factor_inputs: ticker -> dict with
    relative_volume/technical_momentum/sector_strength (default 0.5)."""
    enriched: list[EnrichedPick] = []
    for profile, rec in inputs:
        opt = options_map.get(rec.ticker)
        fi = factor_inputs.get(rec.ticker, {})
        fs = factor_score(profile, opt,
                          fi.get("relative_volume", 0.5),
                          fi.get("technical_momentum", 0.5),
                          fi.get("sector_strength", 0.5), cfg)
        conv = conviction(fs, rec.composite_score, cfg)
        ev_rank = expected_value_rank(profile.expected_return_pct,
                                      profile.prob_gain, conv)
        size = kelly_size(profile.kelly_fraction, cfg)
        ok = passes_profit_gate(rec.composite_score, profile.expected_return_pct,
                                profile.prob_gain, profile.risk_reward, cfg)
        rec.expected_return_pct = profile.expected_return_pct
        rec.prob_gain = profile.prob_gain
        rec.ci_low_pct = profile.ci_low_pct
        rec.ci_high_pct = profile.ci_high_pct
        rec.risk_reward = profile.risk_reward
        rec.risk_score = profile.risk_score
        rec.kelly_fraction = profile.kelly_fraction
        rec.suggested_size_pct = size
        rec.earnings_beat_rate = profile.earnings_beat_rate
        rec.eps_revision_30d_pct = profile.eps_revision_30d_pct
        if opt is not None and opt.available:
            rec.options_summary = json.dumps({
                "iv": opt.implied_volatility,
                "put_call": opt.put_call_ratio,
                "max_pain": opt.max_pain,
                "unusual_call": opt.unusual_call_volume,
                "unusual_put": opt.unusual_put_volume,
                "gamma_proxy": opt.gamma_proxy,
            })
        enriched.append(EnrichedPick(rec, profile, opt, ev_rank, size, ok))
    passing = [e for e in enriched if e.passes_profit_gate]
    passing.sort(key=lambda e: e.ev_rank, reverse=True)
    return passing
