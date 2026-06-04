"""Application health check — verifies the database, storage, backups, and that
every QuoteForge scheduled job is registered and not disabled. Designed to run
every few hours and email an alert ONLY when something is wrong.

Run:  python -m quoteforge.admin healthcheck [email]
"""
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from quoteforge.config import OUTPUT_DIR

# The scheduled jobs that should exist (Windows Task Scheduler names)
EXPECTED_TASKS = [
    "QuoteForge Daily Report",
    "QuoteForge Weekly Report",
    "QuoteForge Monthly Report",
    "QuoteForge Yearly Report",
    "QuoteForge Daily Backup",
    "QuoteForge Health Check",
]

HEALTH_LOG = OUTPUT_DIR / "health_log.json"


@dataclass
class Check:
    name: str
    status: str   # "OK" | "WARN" | "FAIL"
    detail: str = ""


# ── Individual checks ────────────────────────────────────────────

def check_database() -> Check:
    try:
        from quoteforge.db.database import init_db, get_order_stats
        init_db()
        stats = get_order_stats()
        return Check("Database", "OK", f"{stats['total']} orders reachable")
    except Exception as exc:  # noqa: BLE001
        return Check("Database", "FAIL", f"{type(exc).__name__}: {exc}")


def check_storage() -> Check:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        probe = OUTPUT_DIR / ".health_probe"
        probe.write_text("ok")
        probe.unlink()
        return Check("Storage", "OK", f"{OUTPUT_DIR} writable")
    except Exception as exc:  # noqa: BLE001
        return Check("Storage", "FAIL", f"cannot write to output dir: {exc}")


def check_recent_backup(max_age_hours: int = 48) -> Check:
    try:
        from quoteforge.db.database import list_backups
        backups = list_backups()
        if not backups:
            return Check("DB Backup", "WARN", "no backups found yet")
        newest = backups[0]
        age_h = (datetime.now() - datetime.fromtimestamp(newest.stat().st_mtime))
        if age_h <= timedelta(hours=max_age_hours):
            return Check("DB Backup", "OK", f"latest {newest.name}")
        return Check("DB Backup", "WARN",
                     f"newest backup is older than {max_age_hours}h")
    except Exception as exc:  # noqa: BLE001
        return Check("DB Backup", "WARN", str(exc))


def check_error_orders() -> Check:
    try:
        from quoteforge.db.database import get_orders_by_status
        errored = get_orders_by_status("error")
        if not errored:
            return Check("Order Errors", "OK", "no errored orders")
        ids = ", ".join(o["order_id"] for o in errored[:5])
        return Check("Order Errors", "WARN",
                     f"{len(errored)} order(s) in error: {ids}")
    except Exception as exc:  # noqa: BLE001
        return Check("Order Errors", "WARN", str(exc))


def _query_windows_tasks() -> dict[str, str]:
    """Return {task_name: state} from Windows Task Scheduler. Empty on failure."""
    try:
        out = subprocess.run(
            ["schtasks", "/Query", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception:  # noqa: BLE001 - non-Windows or schtasks missing
        return {}
    tasks: dict[str, str] = {}
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 3:
            name = parts[0].strip('"').lstrip("\\")
            state = parts[2].strip('"')
            tasks[name] = state
    return tasks


def check_scheduled_jobs(query_fn: Optional[Callable[[], dict]] = None) -> Check:
    """Verify the expected scheduled jobs exist and aren't Disabled."""
    query_fn = query_fn or _query_windows_tasks
    tasks = query_fn()
    if not tasks:
        return Check("Scheduled Jobs", "WARN",
                     "could not read Task Scheduler (non-Windows or none set)")
    missing = [t for t in EXPECTED_TASKS if t not in tasks]
    disabled = [t for t in EXPECTED_TASKS
                if tasks.get(t, "").lower() == "disabled"]
    if missing or disabled:
        problems = []
        if missing:
            problems.append("missing: " + ", ".join(missing))
        if disabled:
            problems.append("disabled: " + ", ".join(disabled))
        return Check("Scheduled Jobs", "FAIL", "; ".join(problems))
    return Check("Scheduled Jobs", "OK",
                 f"{len(EXPECTED_TASKS)} jobs registered and enabled")


# ── Aggregate ────────────────────────────────────────────────────

def run_healthcheck(query_fn: Optional[Callable[[], dict]] = None) -> dict:
    checks = [
        check_database(),
        check_storage(),
        check_recent_backup(),
        check_error_orders(),
        check_scheduled_jobs(query_fn),
    ]
    fails = [c for c in checks if c.status == "FAIL"]
    warns = [c for c in checks if c.status == "WARN"]
    overall = "FAIL" if fails else ("WARN" if warns else "OK")
    result = {
        "overall": overall,
        "timestamp": datetime.now().isoformat(),
        "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                   for c in checks],
        "problem_count": len(fails) + len(warns),
    }
    _append_health_log(result)
    return result


def _append_health_log(result: dict) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        entries = []
        if HEALTH_LOG.exists():
            entries = json.loads(HEALTH_LOG.read_text())
        entries.append(result)
        # keep the last 200 runs
        HEALTH_LOG.write_text(json.dumps(entries[-200:], indent=2))
    except Exception:  # noqa: BLE001
        pass


def format_health_text(result: dict) -> str:
    lines = [f"QuoteForge Health Check — {result['overall']}",
             result["timestamp"], "-" * 44]
    for c in result["checks"]:
        icon = {"OK": "[OK]  ", "WARN": "[WARN]", "FAIL": "[FAIL]"}[c["status"]]
        lines.append(f"{icon} {c['name']}: {c['detail']}")
    return "\n".join(lines)


def send_health_alert(query_fn: Optional[Callable[[], dict]] = None,
                      always: bool = False) -> dict:
    """Run the health check and email an alert if there are problems.

    always=True sends even when everything is OK (useful for a manual test).
    """
    result = run_healthcheck(query_fn)
    if result["overall"] == "OK" and not always:
        return {"status": "ok_no_alert", "result": result}

    from quoteforge.automation.emailer import _send_email
    subject = f"⚠️ QuoteForge Health: {result['overall']} ({result['problem_count']} issue(s))"
    body = (f"<html><body style='font-family:Arial'>"
            f"<pre style='font-size:14px'>{format_health_text(result)}</pre>"
            f"</body></html>")
    email_status = _send_email(subject, body)
    return {"status": "alert_sent" if email_status["status"] == "sent"
            else email_status["status"], "result": result}
