"""Automated apparel print calibration - vision QA + a capped, auto-reverting gate.

Removes the owner's DAILY print-validation labor without making a vision model the sole
unchecked authority over real garments (the highest-risk link in zero-owner iteration).

Flow:
  1. A PHYSICAL apparel test print is received; evidence photo(s) are graded by vision QA
     against the intended design - placement, size, alignment, colour, safe zone.
  2. If the QA score clears CALIBRATION_MIN_QA_SCORE AND the owner has turned on the
     one-time AUTO_CALIBRATION_ENABLED consent, a vision-approved calibration row is
     written and apparel production OPENS - but only within safety rails.
  3. Safety rails (auto_calibration_active, read live by the router):
       - AUTO_CALIBRATION_ENABLED must be on (a one-time owner consent, not daily labour).
       - A non-revoked vision-approved row must exist.
       - Fewer than CALIBRATION_UNIT_CAP apparel units produced since (a bounded blast
         radius before a re-confirm).
       - NO apparel return / dispute / cancel since calibration (auto-revert tripwire).
     If any rail fails, the gate is CLOSED again automatically - apparel re-blocks at the
     router with no owner action.
  4. A failing QA never opens the gate; it blocks apparel and opens an owner issue.

The env master APPAREL_PRINT_CALIBRATED still forces apparel open on its own (the manual
path is unchanged). This module only adds a REVERSIBLE, DB-driven path. Everything is
fail-safe: if the safety state can't be verified, auto_calibration_active returns False
(apparel stays blocked) - unverifiable is never treated as safe.
"""
from __future__ import annotations

import logging

from quoteforge.db.database import _conn

logger = logging.getLogger(__name__)

_VISION_APPROVER = "vision-qa:auto"
# The QA dimensions a physical apparel print must satisfy (reported per-check).
_QA_CHECKS = ("placement", "size", "alignment", "colour", "safe_zone")


def _auto_enabled() -> bool:
    """The one-time owner consent that this automation may open apparel production."""
    from quoteforge.config import AUTO_CALIBRATION_ENABLED
    return bool(AUTO_CALIBRATION_ENABLED)


# ── Vision QA of a physical test print ───────────────────────────

def grade_test_print(evidence_urls: list[str], *, expected_design_url: str = "",
                     product_uid: str = "", grader=None) -> dict:
    """Grade a physical apparel test print from evidence photo(s) against the intended
    design. Returns {skipped|score, passed, checks, detail}. Never raises.

    Gated: in TEST_MODE (or with no evidence) it is a no-op ('skipped') so it never
    fabricates a pass. `grader` is an injectable callable(evidence_urls, expected_design_url,
    product_uid)->{score, checks} for testing / to swap the vision backend; when omitted the
    default AI vision grader is used (only live)."""
    from quoteforge.config import TEST_MODE, CALIBRATION_MIN_QA_SCORE
    if not evidence_urls:
        return {"skipped": True, "passed": False, "detail": "no evidence photo provided"}
    if grader is None and TEST_MODE:
        return {"skipped": True, "passed": False,
                "detail": "TEST_MODE - vision QA is a no-op (never auto-passes)"}
    try:
        g = grader or _default_vision_grader
        result = g(evidence_urls, expected_design_url, product_uid) or {}
        score = float(result.get("score", 0.0) or 0.0)
        checks = {k: bool(result.get("checks", {}).get(k, False)) for k in _QA_CHECKS}
        passed = score >= float(CALIBRATION_MIN_QA_SCORE) and all(checks.values())
        return {"skipped": False, "score": round(score, 4), "passed": passed,
                "checks": checks, "detail": result.get("detail", "")}
    except Exception as exc:  # noqa: BLE001 - a QA error never counts as a pass
        logger.warning("vision QA failed (treated as NOT passed): %s", exc)
        return {"skipped": False, "score": 0.0, "passed": False,
                "checks": {k: False for k in _QA_CHECKS}, "detail": f"qa error: {exc}"}


def _default_vision_grader(evidence_urls: list[str], expected_design_url: str,
                           product_uid: str) -> dict:
    """Live AI-vision grader (only reached outside TEST_MODE). Defensive: returns a 0
    score on anything unexpected so a failure can never open the gate. The exact vision
    prompt/parse is confirmed against real evidence at go-live."""
    try:
        from quoteforge.ai.vision_qa import grade_print_evidence  # optional live backend
        return grade_print_evidence(evidence_urls, expected_design_url, product_uid)
    except Exception as exc:  # noqa: BLE001 - no backend / call failed -> not passed
        logger.warning("default vision grader unavailable: %s", exc)
        return {"score": 0.0, "checks": {}, "detail": f"no vision backend: {exc}"}


# ── Calibration ledger (auto approve / revoke) ───────────────────

def record_vision_calibration(product_uid: str, qa: dict) -> dict:
    """Write a VISION-approved calibration row when QA passed (auto path). Returns the row,
    or {} if QA did not pass (never opens the gate on a non-pass)."""
    if not qa.get("passed"):
        return {}
    product_uid = (product_uid or "").strip()
    if not product_uid or product_uid.upper().startswith("GEL-"):
        return {}
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO apparel_print_calibration (product_family, product_uid, status,
                approver, notes, approved_at, created_at)
            VALUES ('apparel', ?, 'approved', ?, ?, datetime('now'), datetime('now'))
        """, (product_uid, _VISION_APPROVER, f"vision QA score={qa.get('score')}"))
        row = conn.execute("SELECT * FROM apparel_print_calibration WHERE id=?",
                           (cur.lastrowid,)).fetchone()
    logger.info("auto-calibration: vision-approved %s (score=%s)", product_uid, qa.get("score"))
    return dict(row)


def _active_vision_rows() -> list[dict]:
    """Non-revoked vision-approved calibration rows, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM apparel_print_calibration WHERE approver=? AND status='approved' "
            "ORDER BY id DESC", (_VISION_APPROVER,)).fetchall()
    return [dict(r) for r in rows]


def revert_calibration(reason: str) -> int:
    """Auto-revert: revoke every active vision-approved row (re-blocks apparel at the
    router) and record why. Returns how many rows were revoked. Owner ('approved' by a
    human) rows are untouched - only the automated path is reverted."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE apparel_print_calibration SET status='revoked', "
            "notes=notes || ' | REVERTED: ' || ? WHERE approver=? AND status='approved'",
            (reason[:200], _VISION_APPROVER))
        n = cur.rowcount or 0
    if n:
        logger.warning("auto-calibration REVERTED %d row(s): %s", n, reason)
    return n


# ── Safety rails (read live by the router) ───────────────────────

def _apparel_units_since(ts: str) -> int:
    """Count apparel orders created since a timestamp (the cap's denominator). Fail-safe:
    on any error return a large number so the cap trips (blocks) rather than over-runs."""
    try:
        with _conn() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE lower(product_type)='apparel' "
                "AND created_at >= ?", (ts,)).fetchone()["n"])
    except Exception as exc:  # noqa: BLE001 - unknown count -> assume over cap (block)
        logger.warning("apparel unit count failed (assuming over-cap): %s", exc)
        return 10 ** 9


def _apparel_issue_since(ts: str) -> str:
    """A return/dispute/cancel/refund on an apparel order since `ts` -> the auto-revert
    trigger. Returns a reason string, or '' if none. Fail-safe: on error return a reason
    (treat as an issue -> revert), because an unverifiable safety state is not safe."""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT status FROM orders WHERE lower(product_type)='apparel' "
                "AND created_at >= ? AND lower(status) IN "
                "('returned','return','disputed','dispute','cancelled','canceled','refunded') "
                "LIMIT 1", (ts,)).fetchone()
        return f"apparel order status={row['status']}" if row else ""
    except Exception as exc:  # noqa: BLE001 - unknown -> treat as an issue (revert)
        logger.warning("apparel issue scan failed (assuming issue): %s", exc)
        return f"issue scan error: {exc}"


def auto_calibration_active() -> bool:
    """The router-facing gate for the AUTOMATED path. True ONLY when every safety rail
    holds; False (apparel blocked) otherwise. Never raises; fail-safe to False."""
    try:
        if not _auto_enabled():
            return False
        rows = _active_vision_rows()
        if not rows:
            return False
        from quoteforge.config import CALIBRATION_UNIT_CAP
        since = rows[-1].get("approved_at") or rows[-1].get("created_at") or ""
        if _apparel_issue_since(since):          # a dispute/return -> auto-revert territory
            return False
        if _apparel_units_since(since) >= int(CALIBRATION_UNIT_CAP):
            return False                          # bounded blast radius before re-confirm
        return True
    except Exception as exc:  # noqa: BLE001 - unverifiable safety state -> blocked
        logger.warning("auto_calibration_active fail-safe to False: %s", exc)
        return False


def check_auto_revert() -> dict:
    """Tripwire (daily / post-order): if the automated calibration is live but a safety
    rail has since failed, REVERT it and alert. Returns {reverted, reason}."""
    if not (_auto_enabled() and _active_vision_rows()):
        return {"reverted": 0, "reason": "no active auto-calibration"}
    rows = _active_vision_rows()
    since = rows[-1].get("approved_at") or rows[-1].get("created_at") or ""
    reason = _apparel_issue_since(since)
    if not reason:
        from quoteforge.config import CALIBRATION_UNIT_CAP
        if _apparel_units_since(since) >= int(CALIBRATION_UNIT_CAP):
            reason = f"unit cap {CALIBRATION_UNIT_CAP} reached"
    if reason:
        n = revert_calibration(reason)
        return {"reverted": n, "reason": reason}
    return {"reverted": 0, "reason": "all rails holding"}


def process_test_print_evidence(product_uid: str, evidence_urls: list[str], *,
                                expected_design_url: str = "", grader=None) -> dict:
    """End-to-end: grade the evidence, and on PASS auto-approve (open apparel within the
    rails); on FAIL/skip, keep apparel blocked and open an owner issue. Returns a summary."""
    qa = grade_test_print(evidence_urls, expected_design_url=expected_design_url,
                          product_uid=product_uid, grader=grader)
    if qa.get("passed"):
        row = record_vision_calibration(product_uid, qa)
        return {"action": "auto_calibrated" if row else "no_op", "qa": qa,
                "active": auto_calibration_active()}
    # not passed (or skipped): block + open an issue for the owner
    if not qa.get("skipped"):
        try:
            from quoteforge.db.database import enqueue_approval
            enqueue_approval("apparel_calibration_failed",
                             f"Vision QA failed for {product_uid}: {qa.get('detail')} "
                             f"(score={qa.get('score')}). Apparel stays BLOCKED.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not enqueue calibration-fail issue: %s", exc)
    return {"action": "blocked", "qa": qa, "active": auto_calibration_active()}
