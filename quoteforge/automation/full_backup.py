"""One-shot full backup: database + code (commit + push to GitHub) + bundle.

Keeps everything safe off-machine with zero effort:
  1. snapshot the database (+ prune to the retention window)
  2. commit any tracked code changes (auto-backup commit)
  3. push to GitHub so the work is off-disk
  4. refresh a complete local git bundle (offline restore)

Designed to run nightly (scheduled) and on demand (admin backup-all). Git steps
are best-effort and only touch ALREADY-TRACKED files (git add -u), so untracked
junk/secrets are never committed; .env stays gitignored.
"""
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _git(args: list[str], runner=subprocess.run) -> tuple[int, str]:
    """Run a git command in the project root; returns (exit_code, combined output).
    ``runner`` is injectable so tests can fake git without touching the repo."""
    try:
        p = runner(["git", *args], cwd=str(PROJECT_ROOT),
                   capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


def run_full_backup(push: bool = True, auto_commit: bool = True,
                    runner=subprocess.run) -> dict:
    """The nightly full backup: DB snapshot -> auto-commit tracked changes ->
    push to GitHub -> refresh the local git bundle -> optional Drive upload.
    Returns a result dict consumed by format_backup_text()."""
    result = {"timestamp": datetime.now().isoformat(timespec="seconds")}

    # 1. Database snapshot + prune.
    try:
        from quoteforge.db.database import backup_database, prune_old_backups
        dbpath = backup_database()
        pruned = prune_old_backups()
        result["db_backup"] = str(dbpath) if dbpath else "no database"
        result["db_pruned"] = pruned
    except Exception as exc:  # noqa: BLE001
        result["db_backup"] = f"error: {exc}"

    # 2. Auto-commit tracked changes (modifications/deletions only).
    if auto_commit:
        _git(["add", "-u"], runner)
        code, _ = _git(["diff", "--cached", "--quiet"], runner)  # 1 = staged changes
        if code == 1:
            msg = f"chore: auto-backup {datetime.now():%Y-%m-%d %H:%M}"
            c, out = _git(["commit", "-m", msg], runner)
            result["auto_commit"] = "committed" if c == 0 else f"failed: {out[:120]}"
        else:
            result["auto_commit"] = "nothing to commit"

    # 3. Push to GitHub.
    if push:
        c, out = _git(["push", "origin", "HEAD"], runner)
        result["push"] = "pushed" if c == 0 else f"failed: {out.strip()[:160]}"

    # 4. Refresh the complete local bundle.
    try:
        bundles = PROJECT_ROOT / "backups"
        bundles.mkdir(exist_ok=True)
        bundle = bundles / "joffiels_full_backup.bundle"
        c, out = _git(["bundle", "create", str(bundle), "--all"], runner)
        result["bundle"] = str(bundle) if c == 0 else f"failed: {out[:120]}"
    except Exception as exc:  # noqa: BLE001
        result["bundle"] = f"error: {exc}"

    # 5. Off-site copy to Google Drive (optional, best-effort).
    try:
        from quoteforge.config import BACKUP_TO_DRIVE
        if BACKUP_TO_DRIVE:
            from quoteforge.automation.google_drive_client import (
                upload_file_to_drive, is_configured)
            if not is_configured():
                result["offsite"] = "skipped (Drive not configured)"
            else:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                links = []
                db = result.get("db_backup", "")
                if db and Path(db).exists():
                    if upload_file_to_drive(Path(db), f"db_{stamp}.sqlite3"):
                        links.append("db")
                bnd = result.get("bundle", "")
                if bnd and Path(bnd).exists():
                    if upload_file_to_drive(Path(bnd), f"backup_{stamp}.bundle"):
                        links.append("bundle")
                result["offsite"] = (
                    "uploaded " + "+".join(links) if links else "upload failed")
    except Exception as exc:  # noqa: BLE001
        result["offsite"] = f"error: {exc}"

    # Flag any UNTRACKED files the user may want to add manually.
    _, st = _git(["status", "--porcelain", "--untracked-files=normal"], runner)
    untracked = [l for l in st.splitlines() if l.startswith("??")]
    result["untracked_count"] = len(untracked)
    return result


BUNDLE_PATH = PROJECT_ROOT / "backups" / "joffiels_full_backup.bundle"


def restore_all(into: str = "", runner=subprocess.run) -> dict:
    """One-command recovery.

    - Database: restored from the newest snapshot (reversible - the current DB is
      snapshotted first by restore_database()).
    - Code: cloned from the local git bundle into ``into`` (a FRESH directory) when
      given, so we never silently overwrite a working tree. Without ``into`` we just
      report the exact clone command to run.
    """
    result = {"timestamp": datetime.now().isoformat(timespec="seconds")}

    # 1. Database - restore newest snapshot (reversible).
    try:
        from quoteforge.db.database import restore_database
        restored = restore_database()
        result["db_restore"] = str(restored) if restored else "no snapshot found"
    except Exception as exc:  # noqa: BLE001
        result["db_restore"] = f"error: {exc}"

    # 2. Code - clone the bundle into a fresh dir (never overwrite in place).
    if not BUNDLE_PATH.exists():
        result["code_restore"] = f"no bundle at {BUNDLE_PATH} (run backup-all first)"
    elif into:
        dest = Path(into)
        if dest.exists() and any(dest.iterdir()):
            result["code_restore"] = f"refused: {dest} exists and is not empty"
        else:
            c, out = _git(["clone", str(BUNDLE_PATH), str(dest)], runner)
            result["code_restore"] = (f"cloned to {dest}" if c == 0
                                      else f"failed: {out[:160]}")
    else:
        result["code_restore"] = (
            f"bundle ready - restore code with:\n"
            f'      git clone "{BUNDLE_PATH}" <new-folder>')
    return result


def format_restore_text(r: dict) -> str:
    """Human-readable summary of a restore_all() result (printed by the CLI)."""
    return "\n".join([
        "=" * 56, f"RESTORE - {r['timestamp']}", "=" * 56,
        f"  Database : {r.get('db_restore', '-')}",
        f"  Code     : {r.get('code_restore', '-')}",
        "=" * 56,
    ])


def format_backup_text(r: dict) -> str:
    """Human-readable summary of a run_full_backup() result (printed/emailed)."""
    return "\n".join([
        "=" * 56, f"FULL BACKUP - {r['timestamp']}", "=" * 56,
        f"  Database : {r.get('db_backup', '-')}"
        + (f" (pruned {r['db_pruned']})" if r.get("db_pruned") else ""),
        f"  Code     : {r.get('auto_commit', 'skipped')}",
        f"  Push     : {r.get('push', 'skipped')}",
        f"  Bundle   : {r.get('bundle', '-')}",
        f"  Off-site : {r.get('offsite', 'disabled')}",
        f"  Untracked: {r.get('untracked_count', 0)} file(s) not in git "
        f"(add manually if needed)",
        "=" * 56,
    ])
