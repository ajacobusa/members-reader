"""Single source of truth for QuoteForge's scheduled jobs.

This module defines every recurring job ONCE. Both sides read from it:
  - the installer (`admin install-schedule`) creates the Windows Task Scheduler
    entries from these definitions, and
  - the health check (`healthcheck.EXPECTED_TASKS`) verifies the very same names
    are registered and enabled.

Because both derive from `SCHEDULED_JOBS`, the list of jobs that get *created*
and the list that gets *monitored* can never drift apart.

Install all jobs:   python -m quoteforge.admin install-schedule
Preview only:       python -m quoteforge.admin install-schedule --dry-run
Remove all jobs:    python -m quoteforge.admin install-schedule --remove
"""
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Project root = two levels up from this file (…/quoteforge/automation/scheduler.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ScheduledJob:
    name: str                 # Windows Task Scheduler task name
    admin_args: str           # arguments passed to `python -m quoteforge.admin`
    schtasks_flags: list[str] = field(default_factory=list)  # /SC, /MO, /D, /ST …
    description: str = ""


# ── The jobs (the ONE place they are defined) ────────────────────────
# Times are local. Reports run after the US morning; ops jobs run off-peak.
SCHEDULED_JOBS: list[ScheduledJob] = [
    ScheduledJob(
        "QuoteForge Daily Report", "report daily email",
        ["/SC", "DAILY", "/ST", "07:30"],
        "Emails the daily sales report"),
    ScheduledJob(
        "QuoteForge Weekly Report", "report weekly email",
        ["/SC", "WEEKLY", "/D", "MON", "/ST", "07:35"],
        "Emails the weekly sales report (Mondays)"),
    ScheduledJob(
        "QuoteForge Monthly Report", "report monthly email",
        ["/SC", "MONTHLY", "/D", "1", "/ST", "07:40"],
        "Emails the monthly sales report (1st of month)"),
    ScheduledJob(
        "QuoteForge Yearly Report", "report yearly email",
        ["/SC", "MONTHLY", "/MO", "JAN", "/D", "1", "/ST", "07:45"],
        "Emails the yearly sales report (Jan 1)"),
    ScheduledJob(
        "QuoteForge Daily Backup", "backup",
        ["/SC", "DAILY", "/ST", "02:00"],
        "Snapshots the database and prunes old backups"),
    ScheduledJob(
        "QuoteForge Health Check", "healthcheck",
        ["/SC", "HOURLY", "/MO", "5"],
        "Verifies DB/storage/backups/jobs every 5 hours"),
    ScheduledJob(
        "QuoteForge Monthly Campaign", "campaign",
        ["/SC", "MONTHLY", "/D", "1", "/ST", "08:00"],
        "Generates the seasonal campaign plan (1st of month)"),
    ScheduledJob(
        "QuoteForge Weekly Sales Actions", "sales",
        ["/SC", "WEEKLY", "/D", "MON", "/ST", "08:05"],
        "Lists upsell/review/win-back actions to send (Mondays)"),
    ScheduledJob(
        "QuoteForge Daily Maintenance", "maintenance email",
        ["/SC", "DAILY", "/ST", "06:00"],
        "Self-healing agent: checks infra, auto-fixes ops issues, "
        "measures performance, emails a digest with enhancement suggestions"),
    ScheduledJob(
        "QuoteForge Etsy Order Poll", "poll-etsy",
        ["/SC", "MINUTE", "/MO", "10"],
        "Polls Etsy every 10 min for new paid orders and imports them "
        "(no Make/Zapier dependency)"),
    ScheduledJob(
        "QuoteForge Daily API Costs", "costs today email",
        ["/SC", "DAILY", "/ST", "07:50"],
        "Emails a detailed daily breakdown of API (Claude) spend"),
]

# Derived — the monitor reads this so it can never list a job we don't install.
EXPECTED_TASK_NAMES = [j.name for j in SCHEDULED_JOBS]


def _task_run_command(job: ScheduledJob, python: str = None) -> str:
    """The /TR string: cd into the project root, then run the admin subcommand."""
    python = python or sys.executable or "python"
    return (f'cmd /c cd /d "{PROJECT_ROOT}" && '
            f'"{python}" -m quoteforge.admin {job.admin_args}')


def build_create_command(job: ScheduledJob, python: str = None) -> list[str]:
    """The full `schtasks /Create …` argv for one job."""
    return [
        "schtasks", "/Create", "/TN", job.name,
        "/TR", _task_run_command(job, python),
        *job.schtasks_flags, "/F",
    ]


def build_delete_command(job: ScheduledJob) -> list[str]:
    return ["schtasks", "/Delete", "/TN", job.name, "/F"]


def install_schedule(remove: bool = False, dry_run: bool = False,
                     only: list[str] | None = None,
                     runner=subprocess.run) -> dict:
    """Create (or remove) scheduled jobs.

    only: restrict to these job names (used by self-heal to touch just the
    missing/disabled ones instead of churning all of them).
    dry_run prints the commands without executing them. Returns a summary dict.
    """
    jobs = [j for j in SCHEDULED_JOBS if (only is None or j.name in only)]
    results: list[dict] = []
    for job in jobs:
        cmd = build_delete_command(job) if remove \
            else build_create_command(job)
        if dry_run:
            results.append({"job": job.name, "status": "dry-run",
                            "command": " ".join(cmd)})
            continue
        try:
            proc = runner(cmd, capture_output=True, text=True, timeout=30)
            ok = proc.returncode == 0
            results.append({
                "job": job.name,
                "status": "ok" if ok else "error",
                "detail": (proc.stdout or proc.stderr or "").strip(),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"job": job.name, "status": "error",
                            "detail": f"{type(exc).__name__}: {exc}"})
    action = "remove" if remove else "install"
    errors = [r for r in results if r["status"] == "error"]
    return {"action": action, "dry_run": dry_run,
            "total": len(jobs), "errors": len(errors),
            "results": results}


def format_install_text(summary: dict) -> str:
    lines = [f"QuoteForge schedule - {summary['action']}"
             + (" (dry run)" if summary["dry_run"] else ""),
             "-" * 52]
    for r in summary["results"]:
        if summary["dry_run"]:
            lines.append(f"  {r['job']}")
            lines.append(f"      {r['command']}")
        else:
            icon = "[OK]  " if r["status"] == "ok" else "[FAIL]"
            lines.append(f"  {icon} {r['job']}"
                         + (f" — {r['detail']}" if r["status"] == "error" else ""))
    if not summary["dry_run"]:
        lines.append("-" * 52)
        lines.append(f"  {summary['total'] - summary['errors']}/{summary['total']} "
                     f"job(s) {summary['action']}d successfully")
    return "\n".join(lines)
