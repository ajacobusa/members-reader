"""Pure watchdog checks for the autonomous daily pipeline. No I/O here —
callers inject probes/queries so this is fully unit-testable."""
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class MonitorReport:
    issues: list[str] = field(default_factory=list)
    recovered: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return len(self.issues) == 0

    def summary(self) -> str:
        if self.healthy and not self.recovered:
            return "All systems healthy."
        parts = []
        if self.recovered:
            parts.append("Recovered: " + "; ".join(self.recovered))
        if self.issues:
            parts.append("Issues: " + "; ".join(self.issues))
        return " | ".join(parts)


def check_daily_freshness(ran_today: bool, is_trading_day: bool) -> list[str]:
    """Flag a missed run only on trading days."""
    if is_trading_day and not ran_today:
        return ["Missed daily run for today (trading day, no picks/market row found)"]
    return []


def check_log_for_errors(log_text: Optional[str]) -> list[str]:
    if not log_text:
        return []
    bad = [ln.strip() for ln in log_text.splitlines()
           if "ERROR" in ln or "DEGRADED" in ln.upper()]
    if bad:
        return [f"Log shows {len(bad)} error/degraded line(s); latest: {bad[-1][:160]}"]
    return []


def check_data_source(probe_fn: Callable[[], bool]) -> list[str]:
    """probe_fn() returns True if the data source is reachable/working."""
    try:
        ok = probe_fn()
    except Exception as exc:  # noqa: BLE001
        return [f"Data source probe raised: {exc}"]
    return [] if ok else ["Data source (yfinance) probe failed — possible API drift"]


def check_scheduled_tasks(task_names: list[str],
                          query_fn: Callable[[str], Optional[str]]) -> list[str]:
    """query_fn(name) returns the task state string ('Ready'/'Running'/'Disabled')
    or None if the task does not exist."""
    issues = []
    for name in task_names:
        state = query_fn(name)
        if state is None:
            issues.append(f"Scheduled task '{name}' is missing")
        elif str(state).lower() == "disabled":
            issues.append(f"Scheduled task '{name}' is disabled")
    return issues


def build_report(issues: list[str], recovered: list[str]) -> MonitorReport:
    return MonitorReport(issues=list(issues), recovered=list(recovered))
