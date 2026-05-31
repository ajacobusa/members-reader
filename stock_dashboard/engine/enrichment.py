from dataclasses import dataclass
from typing import Optional
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
