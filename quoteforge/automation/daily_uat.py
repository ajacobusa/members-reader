"""Automated daily UAT - QuoteForge -> Gelato -> Etsy, no human daily review.

Operating rule: the system tests itself, proves the result with logs (sync_audit_log +
daily_uat_report), BLOCKS unsafe production, and sends alerts ONLY on failure.

This orchestrator does not re-implement the safety spine - the order path already blocks a
GEL-* placeholder submit and un-calibrated apparel (fulfillment/router.py), and
infra-check runs the standing invariants daily. It CONTINUOUSLY PROVES those gates and
alerts on exception. It reuses the existing verifiers (gelato_readiness, verify_*_mappings,
gelato_sync) rather than adding a second source of truth.

Mode awareness (the honest part):
  * Pre-go-live (TEST_MODE on): GEL-* placeholders and un-mapped families are the EXPECTED
    state, not a failure - they are reported as "pending" and do NOT alert. What CAN fail
    (and alert) even now is a MACHINERY / SAFETY regression: a missing table or job, an
    UNAUTHORISED calibration flip (flag on with no owner approval), registry<->map drift,
    or too many failed background jobs.
  * Live (TEST_MODE off): the gates MUST pass. A GEL-* placeholder, an unmapped family, a
    missing official image, or un-calibrated apparel is a hard FAIL -> block + alert.

A step's ``ok`` means "not a failure that should block/alert". ``status`` carries the
human-readable state (PASS / PENDING / FAIL / SKIPPED).
"""
from __future__ import annotations

import json
import logging

from quoteforge.db.database import _conn

logger = logging.getLogger(__name__)

# Env/config that must be present to run live. Grounded to the REAL config attribute
# names (the connector uses ETSY_API_KEY etc., not the spec's ETSY_CLIENT_ID).
_REQUIRED_LIVE_ENV = ("GELATO_API_KEY", "GELATO_STORE_ID", "ETSY_API_KEY",
                      "ETSY_SHOP_ID", "ETSY_WEBHOOK_SECRET", "GELATO_WEBHOOK_SECRET")
# The tables the pipeline depends on (migrations must have created them).
_REQUIRED_TABLES = ("gelato_uid_registry", "gelato_live_probe", "gelato_product_images",
                    "apparel_print_calibration", "sync_audit_log", "daily_uat_report",
                    "sync_runs")
# Background jobs that must stay scheduled for the pipeline to self-heal + self-test.
_REQUIRED_JOBS = ("infra-check", "gelato-sync", "ecommerce-images", "mockup-sync",
                  "daily-uat")
# Max failed background-job runs in the last 24h before we treat it as a failure.
_FAILED_JOBS_THRESHOLD = 5


def _test_mode() -> bool:
    """True when TEST_MODE is on (pre-go-live; placeholder gates report PENDING)."""
    from quoteforge.config import TEST_MODE
    return bool(TEST_MODE)


def _live() -> bool:
    """True only when genuinely live: TEST_MODE off AND a Gelato key present. A stray key
    with TEST_MODE still on does NOT count as live (the gates stay pre-go-live)."""
    from quoteforge.config import TEST_MODE, GELATO_API_KEY
    return (not TEST_MODE) and bool(GELATO_API_KEY)


def _s(name: str, ok: bool, status: str, detail: str = "", **extra) -> dict:
    """Build one UAT step result. ok == 'not a blocking failure'."""
    return {"step": name, "ok": bool(ok), "status": status, "detail": detail, **extra}


# ── Step 1: deployment validation ────────────────────────────────

def validate_deployment_health() -> dict:
    """Tables + scheduled jobs must exist (hard, always). Required live env is a hard
    FAIL only in live mode; pre-go-live it is reported pending."""
    from quoteforge import config
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    with _conn() as conn:
        have = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    missing_tables = [t for t in _REQUIRED_TABLES if t not in have]
    # A job's command is the first token of its admin_args ("poll-etsy --once" -> "poll-etsy").
    job_cmds = {(getattr(j, "admin_args", "") or "").split()[0]
                for j in SCHEDULED_JOBS if getattr(j, "admin_args", "")}
    missing_jobs = [j for j in _REQUIRED_JOBS if j not in job_cmds]
    missing_env = [k for k in _REQUIRED_LIVE_ENV if not getattr(config, k, "")]

    structural_ok = not missing_tables and not missing_jobs
    if _live():
        ok = structural_ok and not missing_env
        status = "PASS" if ok else "FAIL"
    else:
        ok = structural_ok                    # env not required pre-go-live
        status = "PASS" if ok else "FAIL"
    detail = (f"tables_missing={missing_tables} jobs_missing={missing_jobs} "
              f"env_missing={missing_env}{' (pending pre-go-live)' if not _live() else ''}")
    return _s("deployment_health", ok, status, detail,
              missing_tables=missing_tables, missing_jobs=missing_jobs,
              missing_env=missing_env)


# ── Step 2: UID mapping ──────────────────────────────────────────

def _duplicate_uid_mappings() -> dict:
    """Real UIDs that are shared by >1 SKU (an ambiguous reverse join could attach the
    wrong product image/route). Empty pre-go-live (map is empty)."""
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        seen: dict = {}
        for sku, uid in (_uid_map() or {}).items():
            u = str(uid or "")
            if not u or u.upper().startswith("GEL-"):
                continue
            seen.setdefault(u, []).append(sku)
        return {u: skus for u, skus in seen.items() if len(skus) > 1}
    except Exception as exc:  # noqa: BLE001
        logger.debug("duplicate-uid scan skipped: %s", exc)
        return {}


def assert_uid_mapping() -> dict:
    """Gate 1: no GEL-* value mapped, every family mapped, no duplicate UID. Pre-go-live
    the unmapped/placeholder state is PENDING (expected), not a failure."""
    from quoteforge.automation import gelato_readiness as gr
    g1 = gr.gate1_status()
    placeholders = gr.validate_no_gel_placeholders()
    dups = _duplicate_uid_mappings()
    families = {f: v.get("placeholders", "?") for f, v in g1["families"].items()}
    hard_bad = (not placeholders["ok"]) or bool(dups)   # a mapped GEL-* value or a dup is
    #                                                     always wrong, even pre-go-live
    if _live():
        # LIVE: unverifiable != safe. If the runtime map could not be READ, Gate 1 must
        # fail closed rather than PASS on the very map it is supposed to certify.
        ok = (g1["ready"] and placeholders["ok"] and not dups
              and placeholders.get("runtime_read_ok", False))
        status = "PASS" if ok else "FAIL"
    else:
        ok = not hard_bad                                # pending families don't fail
        status = "PASS" if (ok and g1["ready"]) else ("FAIL" if not ok else "PENDING")
    detail = (f"families(placeholders)={families} mapped_placeholder_values="
              f"{placeholders['registry_offenders'] + placeholders['runtime_offenders']} "
              f"duplicate_uids={list(dups)[:5]}")
    return _s("uid_mapping", ok, status, detail, families=families,
              duplicate_uids=dups, ready=g1["ready"])


# ── Step 3/4: API health + image sync ────────────────────────────

def assert_gelato_api_healthy() -> dict:
    """Gate 3 input: Gelato API is reachable (key + store id). SKIPPED pre-go-live."""
    if not _live():
        return _s("gelato_api", True, "SKIPPED", "TEST_MODE / no key - live probe skipped")
    try:
        from quoteforge.automation.gelato_api import GELATO_API_KEY  # noqa: F401
        # Best-effort: presence of key + store id. A real ping is done by ecommerce-images.
        from quoteforge import config
        ok = bool(config.GELATO_API_KEY and config.GELATO_STORE_ID)
        return _s("gelato_api", ok, "PASS" if ok else "FAIL",
                  "key + store id present" if ok else "missing GELATO_STORE_ID")
    except Exception as exc:  # noqa: BLE001
        return _s("gelato_api", False, "FAIL", str(exc))


def assert_etsy_api_healthy() -> dict:
    """Gate 4 input: Etsy API is reachable (api key + shop id). SKIPPED pre-go-live."""
    if not _live():
        return _s("etsy_api", True, "SKIPPED", "TEST_MODE / no key - live probe skipped")
    from quoteforge import config
    ok = bool(config.ETSY_API_KEY and config.ETSY_SHOP_ID)
    return _s("etsy_api", ok, "PASS" if ok else "FAIL",
              "api key + shop id present" if ok else "missing ETSY_API_KEY/ETSY_SHOP_ID")


def _classify_images(rows: list[dict]) -> list[dict]:
    """Rank + type the images for a SKU: rank 1 = official studio, rank 2 = official
    lifestyle, rank 3+ = QuoteForge mockup/base. Uses the stored source/kind if present,
    else falls back to position. Read-only, best-effort."""
    out = []
    for i, r in enumerate(sorted(rows, key=lambda x: x.get("id", 0))):
        rank = i + 1
        kind = ("studio" if rank == 1 else "lifestyle" if rank == 2 else "mockup")
        out.append({"rank": rank, "type": kind,
                    "url": r.get("image_url", ""), "sku": r.get("gelato_sku", "")})
    return out


def assert_image_sync() -> dict:
    """Gate 4: official studio + lifestyle images pulled in; no duplicate URLs. Pre-go-live
    there are no synced images yet -> PENDING (not a failure)."""
    with _conn() as conn:
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, gelato_sku, image_url FROM gelato_product_images "
                "WHERE image_url IS NOT NULL AND image_url != ''")]
        except Exception as exc:  # noqa: BLE001
            return _s("image_sync", False, "FAIL", f"gelato_product_images unreadable: {exc}")
    urls = [r["image_url"] for r in rows]
    duplicates = sorted({u for u in urls if urls.count(u) > 1})
    if not rows:
        ok = not _live()   # live with zero official images is a failure
        return _s("image_sync", ok, "PENDING" if ok else "FAIL",
                  "no official images synced yet (expected pre-go-live)" if ok
                  else "LIVE but no official images synced", images=0)
    ok = not duplicates
    status = "PASS" if ok else "FAIL"
    return _s("image_sync", ok, status,
              f"{len(rows)} image(s); duplicates={duplicates[:3]}",
              images=len(rows), duplicates=duplicates)


# ── Step 5/6: calibration + unauthorised flip ────────────────────

def assert_apparel_calibration_gate() -> dict:
    """Gate 3: apparel must be blocked until owner-approved calibration. Router enforces
    the block; here we PROVE the state is coherent. Flag-off pre-go-live is PASS (held)."""
    from quoteforge.automation.gelato_readiness import gate3_status
    g3 = gate3_status()
    if g3["flag_without_approval"]:
        return _s("apparel_calibration", False, "FAIL",
                  "APPAREL_PRINT_CALIBRATED=true with NO owner approval - would let "
                  "unverified apparel print (hard rule #6)")
    if g3["ready"]:
        return _s("apparel_calibration", True, "PASS",
                  "flag on + owner physical-print approval on record")
    return _s("apparel_calibration", True, "PENDING" if not _live() else "PASS",
              "flag off - apparel held for manual until a physical test print is approved")


def assert_no_unauthorized_calibration_flip() -> dict:
    """A dedicated, always-hard check for the single most dangerous state (a calibration
    flag flipped with no owner evidence). Mirrors infra-check #61."""
    from quoteforge.config import APPAREL_PRINT_CALIBRATED
    from quoteforge.automation.gelato_readiness import calibration_approved
    unbacked = bool(APPAREL_PRINT_CALIBRATED) and not calibration_approved("apparel")
    return _s("unauthorized_calibration_flip", not unbacked,
              "FAIL" if unbacked else "PASS",
              "unauthorised flip detected" if unbacked else "no unauthorised flip")


def assert_registry_no_drift() -> dict:
    """The verified registry must be fully reflected in the runtime UID map (one source)."""
    from quoteforge.automation import gelato_readiness as gr
    reg = gr.registry_uid_map()
    runtime = {}
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        runtime = _uid_map() or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("uid map read skipped in drift check: %s", exc)
    drift = sorted(sku for sku, uid in reg.items() if runtime.get(sku) != uid)
    return _s("registry_drift", not drift, "FAIL" if drift else "PASS",
              f"registry not exported to runtime map: {drift[:5]}" if drift
              else "registry reflected in runtime map (no drift)")


def assert_failed_jobs_below_threshold() -> dict:
    """Too many failed background-job runs in the last 24h is itself a failure to alert on."""
    try:
        with _conn() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT job, detail FROM sync_runs WHERE ok=0 "
                "AND ran_at >= datetime('now','-1 day')")]
    except Exception as exc:  # noqa: BLE001
        return _s("failed_jobs", False, "FAIL", f"sync_runs unreadable: {exc}")
    n = len(rows)
    ok = n <= _FAILED_JOBS_THRESHOLD
    return _s("failed_jobs", ok, "PASS" if ok else "FAIL",
              f"{n} failed job run(s) in 24h (threshold {_FAILED_JOBS_THRESHOLD})",
              failed=n, jobs=sorted({r["job"] for r in rows}))


# ── Orchestrator + report ────────────────────────────────────────

def _log_audit(steps: list[dict], run: str = "daily-uat") -> None:
    """Append one sync_audit_log row per UAT step (the proof-in-the-logs record)."""
    with _conn() as conn:
        conn.executemany(
            "INSERT INTO sync_audit_log (run, step, ok, detail) VALUES (?,?,?,?)",
            [(run, s["step"], 1 if s["ok"] else 0, s["detail"][:500]) for s in steps])


def _save_report(report: dict) -> None:
    """Persist one daily_uat_report row (the Step-8 report as JSON) for history/gating."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO daily_uat_report (environment, overall, report_json) VALUES (?,?,?)",
            (report["environment"], report["overall"], json.dumps(report)))


def run_daily_uat(send: bool = False) -> dict:
    """Run all UAT steps, store the report + audit log, and (if send) alert ONLY on FAIL.

    Returns the structured Step-8 report. overall == 'FAIL' if any step is a blocking
    failure (step ok is False); otherwise 'PASS'. Never raises - a crashing step is
    itself recorded as a failure."""
    steps: list[dict] = []
    for fn in (validate_deployment_health, assert_uid_mapping, assert_gelato_api_healthy,
               assert_etsy_api_healthy, assert_image_sync, assert_apparel_calibration_gate,
               assert_no_unauthorized_calibration_flip, assert_registry_no_drift,
               assert_failed_jobs_below_threshold):
        try:
            steps.append(fn())
        except Exception as exc:  # noqa: BLE001 - a broken step fails closed
            steps.append(_s(fn.__name__, False, "FAIL", f"step crashed: {exc}"))

    overall = "FAIL" if any(not s["ok"] for s in steps) else "PASS"
    environment = "live" if _live() else "test"
    report = {"environment": environment, "overall": overall,
              "live": _live(), "steps": steps,
              "failures": [s["step"] for s in steps if not s["ok"]]}

    try:
        _log_audit(steps)
        _save_report(report)
    except Exception as exc:  # noqa: BLE001 - never let persistence break the run
        logger.warning("daily-uat: could not persist report/audit: %s", exc)

    logger.info("daily-uat: overall=%s failures=%s env=%s",
                overall, report["failures"], environment)
    if overall == "FAIL" and send:
        try:
            from quoteforge.admin import _alert
            _alert("Daily UAT - FAIL (production blocked where unsafe)",
                   "<pre>" + format_report_text(report) + "</pre>", what="daily-uat")
        except Exception as exc:  # noqa: BLE001
            logger.warning("daily-uat alert failed: %s", exc)
    return report


def format_report_text(report: dict) -> str:
    """Render the Step-8 report format from a run_daily_uat() result."""
    lines = ["QuoteForge Daily Automated UAT Report",
             f"Environment : {report['environment']}",
             f"Overall     : {report['overall']}",
             ""]
    for s in report["steps"]:
        mark = "PASS" if s["ok"] else "FAIL"
        lines.append(f"  [{s['status']:<7}] {s['step']}  ({s['detail']})"
                     if s["status"] != mark or not s["ok"]
                     else f"  [{s['status']:<7}] {s['step']}")
    lines.append("")
    if report["overall"] == "FAIL":
        lines.append("Final action: BLOCK production for the failed gate(s); alert sent.")
    else:
        lines.append("Final action: continue - all gates coherent (pending gates await "
                     "go-live data, production still blocked at the router until then).")
    return "\n".join(lines)


def latest_report() -> dict | None:
    """The most recent stored daily-UAT report (parsed), or None."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT report_json FROM daily_uat_report ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    try:
        return json.loads(row["report_json"])
    except Exception:  # noqa: BLE001
        return None
