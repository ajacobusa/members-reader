"""Auto-resume: schedule a one-shot Windows task to re-run the daily pipeline
exactly when an exhausted data quota resets, then clean itself up.

The regular pipeline is driven by a recurring Windows Task Scheduler job. When a
run is starved because every price source is rate-limited, the runner calls
`schedule_resume(reset_at)` here, which creates a single ONE-TIME task that fires
at the reset moment and runs `run_daily.py` again. A subsequent successful run
calls `cancel_resume()` to remove it.

All schtasks calls fail soft (return False) so a scheduling hiccup never crashes
the pipeline.
"""
import logging
import subprocess
import sys
import datetime as dt
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

TASK_NAME = "StockBoardResume"


def _to_local(at: dt.datetime) -> dt.datetime:
    """Convert a (possibly tz-aware) datetime to local naive time for schtasks."""
    if at.tzinfo is not None:
        at = at.astimezone()  # system local tz
    return at.replace(tzinfo=None)


def build_create_cmd(at: dt.datetime, root: Path,
                     python: Optional[str] = None) -> list[str]:
    """Build the schtasks command that creates the one-shot resume task."""
    local = _to_local(at)
    py = python or sys.executable
    runner = str(Path(root) / "run_daily.py")
    tr = f'"{py}" "{runner}"'
    return [
        "schtasks", "/create", "/tn", TASK_NAME,
        "/sc", "ONCE",
        "/st", local.strftime("%H:%M"),
        "/sd", local.strftime("%m/%d/%Y"),
        "/tr", tr,
        "/f",  # overwrite if it already exists
    ]


def schedule_resume(at: dt.datetime, root: Path, *, python: Optional[str] = None,
                    run=subprocess.run) -> bool:
    """Create/overwrite the one-shot resume task to fire at `at`. Soft-fails."""
    cmd = build_create_cmd(at, root, python)
    try:
        res = run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            log.info("auto-resume scheduled for %s (task %s)",
                     _to_local(at).isoformat(timespec="minutes"), TASK_NAME)
            return True
        log.warning("schedule_resume failed (rc=%s): %s",
                    res.returncode, (res.stderr or res.stdout or "").strip())
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("schedule_resume error: %s", exc)
        return False


def cancel_resume(*, run=subprocess.run) -> bool:
    """Delete the one-shot resume task if present. Soft-fails (incl. 'not found')."""
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    try:
        res = run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            log.info("pending auto-resume task cleared")
            return True
        return False  # typically "task does not exist" — fine
    except Exception as exc:  # noqa: BLE001
        log.warning("cancel_resume error: %s", exc)
        return False
