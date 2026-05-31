import math
from dataclasses import dataclass
from stock_dashboard.db.database import PickRecord
from stock_dashboard.engine.config_loader import Config


@dataclass
class HealthReport:
    total_tickers: int
    fetched: int
    options_covered: int
    earnings_covered: int
    gate_survivors: int
    sanity_failures: int
    market_data_ok: bool

    @property
    def fetch_rate(self) -> float:
        return self.fetched / self.total_tickers if self.total_tickers else 0.0

    def summary(self) -> str:
        return (f"Fetched {self.fetched}/{self.total_tickers} "
                f"({self.fetch_rate*100:.1f}%) · "
                f"options {self.options_covered} · earnings {self.earnings_covered} · "
                f"survivors {self.gate_survivors} · "
                f"{self.sanity_failures} sanity failures")


def _is_bad(x) -> bool:
    return x is not None and isinstance(x, float) and (math.isnan(x) or math.isinf(x))


def sanity_check_pick(rec: PickRecord) -> list[str]:
    problems: list[str] = []
    if rec.price is None or rec.price <= 0:
        problems.append("nonpositive_price")
    for name in ("expected_return_pct", "prob_gain", "ci_low_pct", "ci_high_pct",
                 "suggested_size_pct"):
        if _is_bad(getattr(rec, name, None)):
            problems.append(f"nan_{name}")
    if rec.prob_gain is not None and not (0.0 <= rec.prob_gain <= 1.0):
        problems.append("prob_out_of_range")
    if (rec.ci_low_pct is not None and rec.ci_high_pct is not None
            and rec.ci_low_pct > rec.ci_high_pct):
        problems.append("ci_inverted")
    return problems


def is_degraded(report: HealthReport, cfg: Config) -> bool:
    h = cfg.health
    if h.get("abort_if_no_market_data", True) and not report.market_data_ok:
        return True
    return report.fetch_rate < float(h["min_fetch_success_rate"])
