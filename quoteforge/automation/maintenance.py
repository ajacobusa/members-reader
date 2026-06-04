"""Daily self-healing maintenance agent.

Runs once a day (scheduled), and on every run it:

  1. CHECKS  the infrastructure (DB, storage, backups, scheduled jobs, errors)
  2. FIXES   the operational problems it is SAFE to fix unattended:
       - missing/disabled scheduled jobs  -> re-install them
       - stale or absent backup           -> take a fresh backup
       - database bloat / fragmentation    -> VACUUM + WAL checkpoint
       - integrity problems                -> flag loudly (never auto-"repair")
  3. MEASURES performance (DB size, query latency, reclaimed space)
  4. SUGGESTS enhancements based on the live state (volume, errors, tiers)
  5. EMAILS  a single daily digest of everything it did and recommends.

Deliberate boundaries — this agent NEVER:
  - edits application code or "improves" logic on its own,
  - spends money or flips paid subscriptions,
  - deletes orders or customer data,
  - touches anything when integrity_check fails (it stops and alerts instead).

Those require a human. Everything here is reversible and operational.

Run:  python -m quoteforge.admin maintenance          # heal + print digest
      python -m quoteforge.admin maintenance email     # also email the digest
      python -m quoteforge.admin maintenance --check    # report only, fix nothing
"""
import time
from datetime import datetime
from typing import Optional


# ── Performance measurement ──────────────────────────────────────

def measure_performance() -> dict:
    """Cheap latency probe + DB size, so we can spot regressions over time."""
    from quoteforge.db.database import init_db, get_order_stats, DB_PATH
    init_db()
    t0 = time.perf_counter()
    stats = get_order_stats()
    query_ms = round((time.perf_counter() - t0) * 1000, 1)
    size_kb = round(DB_PATH.stat().st_size / 1024, 1) if DB_PATH.exists() else 0.0
    return {
        "orders_total": stats["total"],
        "stats_query_ms": query_ms,
        "db_size_kb": size_kb,
        "by_status": stats["by_status"],
    }


# ── Auto-remediation steps (each returns an action record) ───────

def _heal_scheduled_jobs(check_detail: str, fix: bool) -> Optional[dict]:
    """If jobs are missing/disabled, re-install the whole schedule."""
    if "missing" not in check_detail and "disabled" not in check_detail:
        return None
    if not fix:
        return {"action": "reinstall scheduled jobs", "status": "skipped (--check)",
                "detail": check_detail}
    from quoteforge.automation.scheduler import install_schedule
    summary = install_schedule()
    ok = summary["errors"] == 0
    return {"action": "reinstall scheduled jobs",
            "status": "fixed" if ok else "failed",
            "detail": f"{summary['total'] - summary['errors']}/{summary['total']} "
                      f"jobs (re)created"
                      + ("" if ok else " — run as Administrator")}


def _heal_backup(check_status: str, fix: bool) -> Optional[dict]:
    """If the latest backup is stale/absent, take a fresh one now."""
    if check_status == "OK":
        return None
    if not fix:
        return {"action": "fresh backup", "status": "skipped (--check)"}
    from quoteforge.db.database import backup_database, prune_old_backups
    path = backup_database()
    if not path:
        return {"action": "fresh backup", "status": "skipped",
                "detail": "no database to back up yet"}
    prune_old_backups(keep=14)
    return {"action": "fresh backup", "status": "fixed", "detail": path.name}


def _heal_database(fix: bool) -> dict:
    """VACUUM + integrity check. Integrity failure is reported, never auto-fixed."""
    if not fix:
        return {"action": "db maintenance", "status": "skipped (--check)"}
    from quoteforge.db.database import db_maintenance
    m = db_maintenance()
    if not m["ran"]:
        return {"action": "db maintenance", "status": "skipped",
                "detail": m.get("reason", "")}
    if m["integrity"] != "ok":
        return {"action": "db maintenance", "status": "ALERT",
                "detail": f"integrity_check returned: {m['integrity']} — "
                          f"restore from a backup, do NOT keep writing"}
    return {"action": "db maintenance", "status": "fixed",
            "detail": f"integrity ok; reclaimed {m['reclaimed_kb']} KB "
                      f"({m['size_before_kb']}->{m['size_after_kb']} KB)"}


# ── Enhancement suggestions (heuristics on live state) ───────────

def suggest_enhancements(perf: dict, health: dict) -> list[str]:
    """Look for opportunities given the current numbers. Advisory only."""
    tips: list[str] = []
    total = perf["orders_total"]
    errored = perf["by_status"].get("error", 0)

    if errored:
        tips.append(f"{errored} order(s) stuck in 'error' — run "
                    f"`admin healthcheck` then inspect; consider re-submitting.")
    if perf["stats_query_ms"] > 250:
        tips.append(f"Stats query took {perf['stats_query_ms']}ms — if it keeps "
                    f"rising, add an index on orders(status).")
    if perf["db_size_kb"] > 50_000:
        tips.append("DB over ~50MB — consider archiving orders older than 1 year "
                    "to a separate file to keep queries fast.")
    # Volume-driven growth suggestions tie into the existing advisors.
    if total >= 60:
        tips.append("Order volume is healthy — review `admin tco` and `admin "
                    "launch scale N` to add the next batch of listings.")
    if total >= 100:
        tips.append("At 100+ orders, run `admin report monthly` and check the "
                    "tier advisor for capacity headroom before peak season.")
    # Margin erosion guard — flag any product/set that slipped below the floor
    # (e.g. after a Gelato or Etsy fee increase).
    try:
        from quoteforge.etsy.margin_guard import audit_catalog
        audit = audit_catalog()
        if audit["below_floor"]:
            worst = audit["offenders"][0]
            tips.append(f"{audit['below_floor']} item(s) below the "
                        f"{audit['floor_pct']:.0f}% margin floor "
                        f"(worst: {worst['name']} at {worst['margin_pct']:.0f}%) — "
                        f"run `admin margins` and reprice.")
    except Exception:  # noqa: BLE001
        pass
    # Autopilot — surface anything waiting on a human decision.
    try:
        from quoteforge.automation.autopilot import autopilot_status
        ap = autopilot_status()
        if ap["pending_human"]:
            tips.append(f"{ap['pending_human']} decision(s) awaiting your approval "
                        f"— run `admin approvals` (autopilot auto-handled "
                        f"{ap['auto_last_24h']} in the last 24h).")
    except Exception:  # noqa: BLE001
        pass
    if not tips:
        tips.append("No issues found. Infra is healthy and within performance "
                    "targets - no action needed today.")
    return tips


# ── Orchestrator ─────────────────────────────────────────────────

def run_maintenance(fix: bool = True, query_fn=None) -> dict:
    """Run the full check -> heal -> measure -> suggest cycle."""
    from quoteforge.automation.healthcheck import run_healthcheck

    health = run_healthcheck(query_fn)
    checks = {c["name"]: c for c in health["checks"]}

    actions: list[dict] = []
    jobs = _heal_scheduled_jobs(checks.get("Scheduled Jobs", {}).get("detail", ""), fix)
    if jobs:
        actions.append(jobs)
    backup = _heal_backup(checks.get("DB Backup", {}).get("status", "OK"), fix)
    if backup:
        actions.append(backup)
    actions.append(_heal_database(fix))

    perf = measure_performance()
    suggestions = suggest_enhancements(perf, health)

    alerts = [a for a in actions if a["status"] in ("failed", "ALERT")]
    overall = "ALERT" if (alerts or health["overall"] == "FAIL") else \
        ("ACTION" if any(a["status"] == "fixed" for a in actions) else "OK")

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": "heal" if fix else "check-only",
        "overall": overall,
        "health": health,
        "actions": actions,
        "performance": perf,
        "suggestions": suggestions,
    }


def format_maintenance_text(report: dict) -> str:
    lines = [f"QuoteForge Daily Maintenance - {report['overall']} ({report['mode']})",
             report["timestamp"], "=" * 56,
             "INFRASTRUCTURE:"]
    for c in report["health"]["checks"]:
        icon = {"OK": "[OK]  ", "WARN": "[WARN]", "FAIL": "[FAIL]"}[c["status"]]
        lines.append(f"  {icon} {c['name']}: {c['detail']}")

    lines.append("\nAUTO-FIXES APPLIED:")
    if report["actions"]:
        for a in report["actions"]:
            lines.append(f"  - {a['action']}: {a['status']}"
                         + (f" ({a['detail']})" if a.get("detail") else ""))
    else:
        lines.append("  (nothing needed fixing)")

    p = report["performance"]
    lines.append("\nPERFORMANCE:")
    lines.append(f"  Orders            : {p['orders_total']}")
    lines.append(f"  Stats query       : {p['stats_query_ms']} ms")
    lines.append(f"  Database size     : {p['db_size_kb']} KB")

    lines.append("\nENHANCEMENT SUGGESTIONS:")
    for s in report["suggestions"]:
        lines.append(f"  * {s}")
    lines.append("=" * 56)
    return "\n".join(lines)


def send_maintenance_digest(fix: bool = True, query_fn=None,
                            always: bool = True) -> dict:
    """Run maintenance and email the digest. always=False only emails on problems."""
    report = run_maintenance(fix, query_fn)
    if report["overall"] == "OK" and not always:
        return {"status": "ok_no_email", "report": report}
    from quoteforge.automation.emailer import _send_email
    subject = f"QuoteForge Maintenance: {report['overall']} — {report['timestamp'][:10]}"
    body = (f"<html><body style='font-family:Arial'>"
            f"<pre style='font-size:13px'>{format_maintenance_text(report)}</pre>"
            f"</body></html>")
    email = _send_email(subject, body)
    return {"status": email["status"], "report": report}
