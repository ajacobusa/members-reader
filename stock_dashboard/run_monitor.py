#!/usr/bin/env python3
"""Autonomous watchdog entry point (Task Scheduler). Checks pipeline health,
auto-recovers a missed daily run once, emails an alert only if unresolved."""
import datetime
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))
logging.basicConfig(filename=ROOT / "logs" / "monitor.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RECOVERY_MARKER = ROOT / "logs" / "recovery_attempted.txt"


def _is_trading_day() -> bool:
    try:
        import exchange_calendars as xcals
        return xcals.get_calendar("XNYS").is_session(datetime.date.today().isoformat())
    except Exception:
        return datetime.date.today().weekday() < 5


def _ran_today(db) -> bool:
    today = datetime.date.today().isoformat()
    try:
        if db.get_market_conditions(today) is not None:
            return True
        return len(db.get_picks(date=today)) > 0
    except Exception:
        return False


def _probe_yfinance() -> bool:
    try:
        import yfinance as yf
        h = yf.Ticker("SPY").history(period="1d")
        return not h.empty
    except Exception:
        return False


def _task_state(name: str):
    try:
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State"],
            capture_output=True, text=True, timeout=20)
        s = (out.stdout or "").strip()
        return s or None
    except Exception:
        return None


def _recovery_attempted_today() -> bool:
    if not RECOVERY_MARKER.exists():
        return False
    return RECOVERY_MARKER.read_text().strip() == datetime.date.today().isoformat()


def _mark_recovery():
    RECOVERY_MARKER.write_text(datetime.date.today().isoformat())


def main() -> None:
    from stock_dashboard.engine.config_loader import load_config
    from stock_dashboard.db.database import Database
    from stock_dashboard.notifier import send_email
    from stock_dashboard.monitor import (
        check_daily_freshness, check_log_for_errors, check_data_source,
        check_scheduled_tasks, build_report,
    )

    cfg = load_config(ROOT / "config.yaml")
    db = Database(str(ROOT / cfg.output["db_path"]))
    db.init_schema()

    trading = _is_trading_day()
    ran = _ran_today(db)
    recovered = []

    # Auto-recover a missed run, at most once per day
    if trading and not ran and not _recovery_attempted_today():
        log.warning("Missed daily run detected — attempting one recovery run")
        _mark_recovery()
        try:
            from stock_dashboard.run_daily import main as run_daily_main
            run_daily_main()
            ran = _ran_today(db)
            if ran:
                recovered.append("Re-ran missed daily pipeline")
        except Exception as exc:  # noqa: BLE001
            log.error("Recovery run failed: %s", exc)

    log_text = ""
    log_path = ROOT / "logs" / "daily.log"
    if log_path.exists():
        log_text = log_path.read_text(errors="ignore")[-8000:]

    issues = []
    issues += check_daily_freshness(ran_today=ran, is_trading_day=trading)
    issues += check_log_for_errors(log_text)
    issues += check_data_source(_probe_yfinance)
    issues += check_scheduled_tasks(["StockBoard Daily", "StockBoard Backtest"],
                                    _task_state)

    report = build_report(issues=issues, recovered=recovered)
    log.info("MONITOR: %s", report.summary())

    if not report.healthy:
        body = (f"<h3>StockBoard watchdog alert</h3><p>{report.summary()}</p>"
                "<p>The system attempted self-recovery where possible. "
                "Items above need a look.</p>")
        send_email("⚠ StockBoard watchdog alert", body, cfg)


if __name__ == "__main__":
    main()
