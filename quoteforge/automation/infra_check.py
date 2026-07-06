"""Infrastructure review agent - a recurring sentinel that re-verifies the automation
invariants (and the fixes that protect hands-free operation) never silently regress.

Runs daily. Each check is a thing that, if it broke, would quietly cripple autonomy:
  - every scheduled job maps to a real handler (a dangling cron job crashes on run)
  - the healthcheck monitors exactly the scheduled jobs (no drift)
  - Etsy OAuth auto-refresh is wired (else intake dies ~1h after go-live)
  - the Etsy poller SURFACES failed imports (else a paid order vanishes silently)
  - the dispute scan DEGRADES on an API error (doesn't crash the job)
  - approved_ready_to_print is surfaced in the needs-action digest
  - the safety guardrails (no auto-refund / claims-human-only / ...) still hold

Plus a DAILY re-check of the critical order-lifecycle invariants that previously
had only a build-time test, so a refactor that silently removes a guard alerts
the owner instead of being discovered after a customer is harmed:
  - no duplicate supplier submission (proof-resume routes via the idempotent router)
  - in-transit is never marked delivered (strict 'delivered'-only confirmation)
  - a review is never requested before delivery
  - a damage claim is never auto-filed without evidence (shared evidence table)
  - shipping-variance detection stays wired (margin-leaking lanes are detectable)
  - no supplier name leaks into any customer surface (generators + storefront)
  - owner per-order emails (invoice on placement, shipped+tracking on ship, delivered)
    are idempotent (flag-guarded, no double notice)
  - no double charge: the router blocks duplicate submission + holds unconfirmed sends
  - product UID integrity: placeholder GEL-* UIDs are detected and never reach production
  - live API keys are gated before go-live + a key-verification command exists
  - every order is assigned a stable customer id, UNIQUE in every case (registry-backed)
  - the shipping-cost review agent stays wired (never silently lose money on shipping)
  - a 12-month calendar is never auto-submitted cover-only (held for manual multi-image)
  - branded items (bottle/tumbler) keep their own placeholder-UID guard
  - apparel multi-area printing (back+sleeves) never loses money + submits every area's file
  - shipping charged separately is collected at cost - an under-collected order is flagged
    at order time (a mis-set Etsy shipping profile can't silently lose money)
  - the daily Gelato cost/discontinued/UID discovery agent is wired + grounded (live API,
    no fabricated numbers, reprices to the margin floor + disables discontinued nightly)

The per-PRODUCT/per-item sweep (SKU<->UID currency, net-margin-floor across every
variation, order-book health) is the sibling daily `daily-qa` agent; this agent
verifies the code invariants that protect every product the same way.

GROWTH PATH: new invariants are DISCOVERED by the code-outcome-auditor (the daily
`audit` sweep flags a module's outcome smells + coverage gaps; the
.claude/agents/code-outcome-auditor subagent then does the deep line-by-line audit
and hands the owner a grounded check to append here). That is how this list grows
without ever lowering the grounding bar below.

GROUNDING (no hallucination): every check is one of three grounded kinds - it RUNS
the real code and observes the outcome (behavioral), it PARSES the real code's AST
(structural, immune to comments/docstrings/dead strings), or it READS real file
content (the leak scan). No check relies on a raw substring-in-source match, which
would pass on a comment or a dead string. Every check FAILS CLOSED: a missing
symbol or an unexpected error raises -> the check reports not-ok -> the owner is
alerted, never a silent false pass.

ALERTS the owner if any check fails. Read-only.
"""
from __future__ import annotations

import ast
import inspect
import logging
import os
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)


def _c(name: str, ok: bool, detail: str) -> dict:
    """One infrastructure check result."""
    return {"name": name, "ok": bool(ok), "detail": detail}


# ── AST grounding helpers ────────────────────────────────────────────
# These verify the SHAPE of real code by parsing it, so a guard mentioned only in
# a comment, a docstring, or a dead string literal can never satisfy a check.

def _tree(obj) -> ast.AST:
    """Parse a function's (or module's) own source into an AST. Raises if the
    source can't be found - the caller's try/except then fails the check closed."""
    return ast.parse(textwrap.dedent(inspect.getsource(obj)))


def _calls(obj, name: str) -> bool:
    """True iff `obj`'s code contains a call to a function named `name`
    (matches both ``name(...)`` and ``something.name(...)``)."""
    for node in ast.walk(_tree(obj)):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == name:
                return True
            if isinstance(f, ast.Attribute) and f.attr == name:
                return True
    return False


def _references(obj, name: str) -> bool:
    """True iff `obj`'s code references a symbol named `name` - whether called
    (``name(...)``), passed as a value (``retry_call(name, ...)``), or accessed as
    an attribute (``mod.name``). Use for a guard invoked indirectly. A name that
    appears only in a comment or a string is NOT a reference, so this can't be
    fooled the way a raw substring match would be."""
    for node in ast.walk(_tree(obj)):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
    return False


def _compares_eq(func, var: str, literal: str) -> bool:
    """True iff `func` has a STRICT equality (``==``) comparing a name `var`
    against the string `literal` - proving e.g. ``st == "delivered"`` rather than
    a substring/``in`` test that would also match 'out_for_delivery'."""
    for node in ast.walk(_tree(func)):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and isinstance(node.ops[0], ast.Eq):
            ends = [node.left, node.comparators[0]]
            names = {n.id for n in ends if isinstance(n, ast.Name)}
            consts = {n.value for n in ends if isinstance(n, ast.Constant)}
            if var in names and literal in consts:
                return True
    return False


def _has_constant(func, value) -> bool:
    """True iff `func`'s code uses `value` as a real constant (not a comment)."""
    return any(isinstance(n, ast.Constant) and n.value == value
               for n in ast.walk(_tree(func)))


def _uses_string(func, needle: str) -> bool:
    """True iff `func` has a string constant CONTAINING `needle` - e.g. a status
    embedded in a SQL ``IN (...)`` fragment. Only executed string literals count;
    a mention in a comment does NOT, so this is grounded, not a substring match."""
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str)
               and needle in n.value
               for n in ast.walk(_tree(func)))


def _has_except(func) -> bool:
    """True iff `func` has an exception handler (degrades instead of crashing)."""
    return any(isinstance(n, ast.ExceptHandler) for n in ast.walk(_tree(func)))


# Framed catalog sizes we INTENTIONALLY do not sell, with the reason. Framed price
# is composed as (bare poster print + frame upcharge), so a framed size needs a
# matching POSTER base to be priced. 16x20 has a prepared framed UID but no 16x20
# poster, so it can't be priced under that model. Owner decision 2026-07-05: leave
# 16x20 framed OFF (safe - no mischarge, no unfulfillable order) rather than add a
# poster size or price it all-in. Invariant #57 lets THIS known gap pass while
# tripping on any NEW prepared framed size that is neither sold nor listed here.
_FRAMED_UNSOLD_OK = {"16x20"}


def check_infrastructure() -> dict:
    """Verify every infrastructure/autonomy invariant. Returns {ok, checks:[...]}.

    Every check is grounded - behavioral (runs the code), structural (parses the
    AST), or a real content scan - and fails closed on any error."""
    checks = []

    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    from quoteforge.admin import COMMANDS
    # 1) Every scheduled job's command maps to a real admin handler. (behavioral)
    dangling = [j.name for j in SCHEDULED_JOBS
                if j.admin_args and j.admin_args.split()[0] not in COMMANDS]
    checks.append(_c("scheduled_jobs_wired", not dangling,
                     f"{len(dangling)} dangling: {dangling[:3]}" if dangling
                     else f"all {len(SCHEDULED_JOBS)} jobs map to a handler"))

    # 2) The healthcheck monitors exactly the scheduled jobs (no drift). (behavioral)
    try:
        from quoteforge.automation.healthcheck import EXPECTED_TASKS
        names = {j.name for j in SCHEDULED_JOBS}
        checks.append(_c("healthcheck_in_sync", set(EXPECTED_TASKS) == names,
                         "EXPECTED_TASKS == scheduled jobs"
                         if set(EXPECTED_TASKS) == names else "drift between the two"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("healthcheck_in_sync", False, str(exc)))

    # 3) Etsy OAuth auto-refresh is wired (the critical go-live fix). (structural:
    #    the API client actually CALLS with_refresh, not just mentions it.)
    try:
        from quoteforge.automation import etsy_api, etsy_auth
        wired = (hasattr(etsy_auth, "refresh_access_token")
                 and _calls(etsy_api, "with_refresh"))
        checks.append(_c("etsy_oauth_refresh_wired", wired,
                         "token auto-refreshes on 401" if wired else "refresh NOT wired"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("etsy_oauth_refresh_wired", False, str(exc)))

    # 4) The Etsy poller surfaces failed imports (paid order never vanishes
    #    silently). (behavioral: actually run poll_once in TEST_MODE.)
    try:
        from quoteforge.automation.etsy_poller import poll_once
        r = poll_once()                       # TEST_MODE -> mock, returns the contract
        checks.append(_c("poller_surfaces_failures", "failed" in r,
                         "poll_once reports a 'failed' list"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("poller_surfaces_failures", False, str(exc)))

    # 5) The dispute scan degrades on an API error (doesn't crash the job).
    #    (structural: the function has a real exception handler.)
    try:
        from quoteforge.automation import dispute_scanner
        guarded = _has_except(dispute_scanner.scan_etsy_disputes)
        checks.append(_c("dispute_scan_guarded", guarded,
                         "scan_etsy_disputes degrades on a fetch error"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("dispute_scan_guarded", False, str(exc)))

    # 6) approved_ready_to_print is surfaced in the needs-action digest.
    #    (structural: the status appears in an executed string - the SQL IN-list
    #    of the report builder - not merely in a comment.)
    try:
        from quoteforge.db import database
        surfaced = _uses_string(database.daily_order_report, "approved_ready_to_print")
        checks.append(_c("approved_ready_surfaced", surfaced,
                         "approved_ready_to_print in needs_attention"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("approved_ready_surfaced", False, str(exc)))

    # 7) The safety guardrails still hold (refunds/claims/margin/address stay
    #    human). (behavioral: run the real rail checks.)
    try:
        from quoteforge.safety_rails import check_safety_rails
        sr = check_safety_rails()
        broken = [x["name"] for x in sr["rails"] if not x["ok"]]
        checks.append(_c("safety_guardrails", sr["ok"],
                         "all guardrails intact" if sr["ok"]
                         else f"WEAKENED: {broken}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("safety_guardrails", False, str(exc)))

    # ── The 14 critical order-lifecycle risks: a DAILY invariant re-check so a
    #    refactor that silently removes a guard is alerted on - not discovered
    #    after a customer is harmed. ───────────────────────────────────────

    # 8) No duplicate supplier submission (risk #2). (structural: the customer-proof
    #    resume path goes through the idempotent router and never references
    #    create_gelato_order - a back-door direct call would double-charge on a
    #    re-run. route_order is invoked indirectly via retry_call(route_order, ...),
    #    so reference-level grounding, not a direct-call match.)
    try:
        from quoteforge.automation.pipeline_orchestrator import (
            resume_after_proof_approval)
        ok = (_references(resume_after_proof_approval, "route_order")
              and not _references(resume_after_proof_approval, "create_gelato_order"))
        checks.append(_c("no_duplicate_supplier_submission", ok,
                         "proof-resume routes through the idempotent router"
                         if ok else "resume path bypasses route_order - DUP RISK"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("no_duplicate_supplier_submission", False, str(exc)))

    # 9) In-transit is never marked delivered (risk #5). (structural: carrier
    #    confirmation gates on a STRICT ``st == "delivered"`` equality, not a
    #    substring that would also fire on 'out_for_delivery'.)
    try:
        from quoteforge.automation.fulfillment_tracker import _carrier_confirm
        ok = _compares_eq(_carrier_confirm, "st", "delivered")
        checks.append(_c("delivery_strict_confirm", ok,
                         "delivery confirmed only on a strict 'delivered'"
                         if ok else "strict 'delivered' equality MISSING"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("delivery_strict_confirm", False, str(exc)))

    # 10) A review is never requested before delivery (risk #6). (behavioral: an
    #     ancient 'shipped' order - excluded ONLY by the pre-delivery guard - must
    #     not be review-due; if the guard were gone it would be returned.)
    try:
        from quoteforge.etsy.delight_loop import delight_due
        probe = {"order_id": "__infra_probe__", "status": "shipped",
                 "delivery_confirmed": 1, "updated_at": "2000-01-01T00:00:00",
                 "delivered_at": "2000-01-01T00:00:00"}
        ok = delight_due([probe]) == []
        checks.append(_c("review_after_delivery_only", ok,
                         "a 'shipped' order is not review-eligible"
                         if ok else "review-before-delivery guard MISSING"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("review_after_delivery_only", False, str(exc)))

    # 11) A damage claim is never auto-filed without evidence (risk #9).
    #     (behavioral: a 'damaged' claim with zero photos must be BLOCKED from
    #     auto-filing; if the evidence gate were bypassed it would return None.)
    try:
        from quoteforge.automation.autopilot import auto_replacement_block_reason
        reason = auto_replacement_block_reason(
            {"category": "damaged"}, {"order_id": "__infra_probe__"})
        ok = reason is not None
        checks.append(_c("claim_evidence_required", ok,
                         "no-evidence damage claim is held for a human"
                         if ok else "evidence gate BYPASSED - auto-file risk"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("claim_evidence_required", False, str(exc)))

    # 12) Shipping-variance detection is wired (risk #12). (behavioral: a wildly
    #     over-cost lane must trip 'leaking' and a clean lane must not.)
    try:
        from quoteforge.etsy.shipping_audit import shipping_variance
        base = {"order_id": "__infra_probe__", "country": "US", "material": "poster"}
        leak = shipping_variance({**base, "shipping_cost": 999.0,
                                  "shipping_collected": 1.0})
        clean = shipping_variance({**base, "shipping_cost": 0.01,
                                   "shipping_collected": 50.0})
        ok = leak["leaking"] is True and clean["leaking"] is False
        checks.append(_c("shipping_variance_wired", ok,
                         "margin-leaking lanes are detected"
                         if ok else "shipping-variance tripwire MISFIRED"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("shipping_variance_wired", False, str(exc)))

    # 13) No supplier name leaks to customers (hard launch constraint). (content
    #     scan: read the real generator source + published storefront.)
    try:
        leaks = _supplier_name_leaks()
        checks.append(_c("no_supplier_name_leak", not leaks,
                         "no supplier name in customer surfaces"
                         if not leaks else f"LEAKED: {leaks[:3]}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("no_supplier_name_leak", False, str(exc)))

    # 14) The critical order-path modules never SILENTLY swallow an error (risk
    #     #2/#14). A swallowed DB write / side-effect there strands an order or
    #     defeats a guard invisibly (e.g. the router's vendor_order_id / unconfirmed
    #     status -> a re-run double-charges). Each module below was audited clean by
    #     the code-outcome-auditor and is pinned here so it can't regress. As more
    #     modules are cleared from the smell backlog, add them to ORDER_PATH_SILENT_FREE.
    #     (behavioral: the real AST smell detector finds zero swallowed excepts.)
    try:
        from quoteforge.automation.code_auditor import audit_module
        ORDER_PATH_SILENT_FREE = ("fulfillment/router.py",
                                  "automation/webhook_server.py",
                                  "automation/pipeline_orchestrator.py",
                                  "db/database.py",
                                  "automation/order_monitor.py",
                                  "automation/autopilot.py",
                                  "automation/etsy_poller.py",
                                  "automation/gelato_api.py",
                                  "fulfillment/claim_workflow.py",
                                  "images/final_qc.py",
                                  "etsy/subscription_product.py")
        offenders = {}
        for m in ORDER_PATH_SILENT_FREE:
            lines = [s["line"] for s in audit_module(m)["smells"]
                     if s["kind"] == "silent_except"]
            if lines:
                offenders[m] = lines
        checks.append(_c("order_path_surfaces_errors", not offenders,
                         f"{len(ORDER_PATH_SILENT_FREE)} order-path modules never "
                         f"swallow an error" if not offenders
                         else f"silent except returned: {offenders}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("order_path_surfaces_errors", False, str(exc)))

    # 15) Runtime / environment health (daemons, ports, workers, hooks, plugins).
    #     A code-invariant check can't see an enabled plugin whose worker daemon is
    #     down blocking the IDE's Read/Edit - the runtime_health agent does, and
    #     tracks known infra issues. Skip-friendly: ok where the dev tooling isn't
    #     present (e.g. the Render host), so this never false-alarms in production.
    try:
        from quoteforge.automation.runtime_health import check_runtime_health
        rh = check_runtime_health()
        bad = [c["name"] for c in rh["checks"] if not c["ok"]]
        checks.append(_c("runtime_health", rh["ok"],
                         f"daemons/ports/hooks/plugins healthy; "
                         f"{len(rh['open_issues'])} tracked issue(s)" if rh["ok"]
                         else f"DEGRADED: {bad}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("runtime_health", False, str(exc)))

    # ── Each MAJOR fix shipped this cycle becomes a guard, so the issue can't
    #    silently return. ───────────────────────────────────────────────────

    # 16) The nightly auto-backup is gated to the default branch - it must NEVER
    #     auto-commit in-progress work on a feature branch (a scheduled 02:00 run
    #     once swept a half-finished change into a chore commit and pushed it).
    #     (structural: run_full_backup reads the current branch and compares 'main'.)
    try:
        from quoteforge.automation.full_backup import run_full_backup
        gated = (_uses_string(run_full_backup, "--abbrev-ref")
                 and _uses_string(run_full_backup, "main"))
        checks.append(_c("backup_gated_to_main", gated,
                         "auto-backup only auto-commits on main"
                         if gated else "auto-backup branch gate MISSING - WIP risk"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("backup_gated_to_main", False, str(exc)))

    # 17) The daily self-monitoring agents actually RUN in production. They were once
    #     defined only in the Windows scheduler and absent from the Render cron, so on
    #     the hosted path they never ran. (content scan: render.yaml wires them.)
    try:
        import quoteforge
        rp = Path(quoteforge.__file__).resolve().parent.parent / "render.yaml"
        if not rp.exists():
            checks.append(_c("guards_automated_in_prod", True,
                             "skipped (no render.yaml present)"))
        else:
            txt = rp.read_text(encoding="utf-8")
            missing = [g for g in ("safety-check", "infra-check", "audit", "daily-qa")
                       if f"quoteforge.admin {g}" not in txt]
            checks.append(_c("guards_automated_in_prod", not missing,
                             "self-monitoring agents wired into the Render cron"
                             if not missing else f"NOT in the Render cron: {missing}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("guards_automated_in_prod", False, str(exc)))

    # 18) No silently-swallowed exception ANYWHERE beyond the accepted baseline - the
    #     whole-codebase ratchet that keeps the silent-failure backlog at zero.
    #     (behavioral: the real AST sweep finds no regression.)
    try:
        from quoteforge.automation.code_auditor import run_full_audit
        regs = run_full_audit(send=False)["regressions"]
        checks.append(_c("no_silent_except_regression", not regs,
                         "no new silent failure beyond baseline"
                         if not regs else f"{len(regs)} new silent failure(s): "
                         f"{[r['module'] for r in regs][:3]}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("no_silent_except_regression", False, str(exc)))

    # 19) The code scanners never recurse into the harness's nested git worktrees
    #     under .claude/worktrees (a stale checkout once leaked its smells + test
    #     files into the sweep and the docs ratchet). (behavioral: list_modules
    #     excludes hidden dirs.)
    try:
        from quoteforge.automation.code_auditor import list_modules
        leaked = [m for m in list_modules()
                  if any(seg.startswith(".") for seg in m.split("/"))]
        checks.append(_c("scans_exclude_worktrees", not leaked,
                         "module sweep excludes hidden/worktree dirs"
                         if not leaked else f"sweep leaked into: {leaked[:3]}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("scans_exclude_worktrees", False, str(exc)))

    # 20) Owner per-order emails are idempotent (no DOUBLE invoice/ship notice on a
    #     webhook retry or re-poll): each send is flag-guarded and the flag is set only
    #     on a confirmed send. (structural, AST: the flag + state literals are used.)
    try:
        from quoteforge.automation import owner_notify
        ok = (_uses_string(owner_notify.send_owner_invoice, "owner_invoice_emailed")
              and _uses_string(owner_notify.send_owner_shipped, "owner_shipped_emailed")
              and _uses_string(owner_notify.send_owner_delivered, "owner_delivered_emailed")
              and _uses_string(owner_notify._notify, "already_sent")
              and _uses_string(owner_notify._notify, "sent"))
        checks.append(_c("owner_notices_idempotent", ok,
                         "owner invoice/ship emails flag-guarded (no double-send)"
                         if ok else "owner-notice idempotency guard missing"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("owner_notices_idempotent", False, str(exc)))

    # 21) No double charge: the router blocks a duplicate supplier submission (returns
    #     'duplicate' when a vendor_order_id already exists) and HOLDS an ambiguous
    #     post-send timeout as 'submit_unconfirmed' rather than blindly re-submitting.
    #     (structural, AST: both anti-double-charge state literals are used.)
    try:
        from quoteforge.fulfillment import router
        impl = router._route_order_impl
        ok = (_uses_string(impl, "vendor_order_id") and _uses_string(impl, "duplicate")
              and _uses_string(impl, "submit_unconfirmed"))
        checks.append(_c("no_double_charge_guard", ok,
                         "router blocks duplicate submission + holds unconfirmed sends"
                         if ok else "double-charge guard weakened"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("no_double_charge_guard", False, str(exc)))

    # 22) Product UID integrity: placeholder GEL-* UIDs are detected (verify_catalog_
    #     mappings) and can never reach production (the router routes a GEL-* UID to
    #     manual). (behavioral: the verifier runs; structural AST: the router uses the
    #     GEL- + manual literals.)
    try:
        from quoteforge.etsy.gelato_catalog import verify_catalog_mappings
        from quoteforge.fulfillment import router
        m = verify_catalog_mappings()
        impl = router._route_order_impl
        ok = (isinstance(m, dict) and "placeholder_count" in m and "all_real" in m
              and _uses_string(impl, "GEL-") and _uses_string(impl, "manual"))
        checks.append(_c("product_uid_integrity", ok,
                         f"UID guard live (placeholders={m.get('placeholder_count')}); "
                         "placeholder UIDs blocked from production"
                         if ok else "UID guard not wired"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("product_uid_integrity", False, str(exc)))

    # 23) Live API keys are gated before go-live (preflight blocks launch on a missing
    #     required key) and there is a live key-verification command. (behavioral: the
    #     real REQUIRED_LIVE_KEYS tuple + the registered admin command.)
    try:
        from quoteforge import preflight
        import quoteforge.admin as admin
        keys = getattr(preflight, "REQUIRED_LIVE_KEYS", ())
        ok = len(keys) >= 4 and "verify-keys" in admin.COMMANDS
        checks.append(_c("api_keys_gated", ok,
                         f"{len(keys)} required keys gated in preflight + verify-keys cmd"
                         if ok else "API-key gate/command missing"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("api_keys_gated", False, str(exc)))

    # 24) Every order is assigned a STABLE customer id (same buyer -> same id) at
    #     creation, for support + repeat-buyer grouping. (behavioral: deriver is stable
    #     + normalized; structural AST: create_order uses the customer_id column.)
    try:
        from quoteforge.db import database as db
        a = db._derive_customer_id("Buyer@Example.com")
        b = db._derive_customer_id("  buyer@example.com ")
        ok = (a.startswith("CUST-") and a == b
              and db._derive_customer_id("", "") == "CUST-anon"
              and _uses_string(db.create_order, "customer_id"))
        checks.append(_c("customer_id_assigned", ok,
                         "stable customer_id assigned per order"
                         if ok else "customer_id assignment missing/unstable"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("customer_id_assigned", False, str(exc)))

    # 25) The shipping-cost review agent is wired (reports the per-product landed cost
    #     basis + flags when a re-verify against the supplier is overdue) so shipping
    #     never quietly loses money. (behavioral: it runs + the command exists.)
    try:
        from quoteforge.automation.shipping_rate_monitor import review_shipping_rates
        import quoteforge.admin as admin
        r = review_shipping_rates()
        ok = (isinstance(r, dict) and "stale" in r and bool(r.get("summary"))
              and "shipping-rate-check" in admin.COMMANDS)
        checks.append(_c("shipping_rate_review_wired", ok,
                         "shipping-cost review agent wired (basis + staleness)"
                         if ok else "shipping-rate review not wired"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("shipping_rate_review_wired", False, str(exc)))

    # 26) customer_id is UNIQUE in every case: same email -> same id, different emails ->
    #     different ids (registry disambiguates any base-hash collision), and an
    #     emailless order gets a per-order-unique anon id. (behavioral: proven against an
    #     ISOLATED temp DB so the live data is never touched.)
    try:
        import tempfile
        from quoteforge.db import database as db
        _orig = db.DB_PATH
        tmp = Path(tempfile.gettempdir()) / f"qf_infra_uidcheck_{os.getpid()}.db"
        try:
            if tmp.exists():
                tmp.unlink()
            db.DB_PATH = tmp
            db.init_db()
            same_a = db.get_or_create_customer("x@a.com")
            same_b = db.get_or_create_customer(" X@A.com ")     # normalized -> same
            diff = db.get_or_create_customer("y@b.com")          # different -> different
            an1 = db.get_or_create_customer("", anon_key="O-1")
            an2 = db.get_or_create_customer("", anon_key="O-2")  # anon -> unique per order
            ok = (same_a == same_b and same_a != diff and an1 != an2)
        finally:
            db.DB_PATH = _orig
            try:
                tmp.unlink(missing_ok=True)
            except OSError as _exc:        # non-fatal temp cleanup; surface, don't swallow
                logger.debug("infra uid-check temp cleanup skipped: %s", _exc)
        checks.append(_c("customer_id_unique", ok,
                         "customer_id unique in every case (stable per buyer, "
                         "collision-disambiguated, anon per order)"
                         if ok else "customer_id uniqueness not guaranteed"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("customer_id_unique", False, str(exc)))

    # 27) A 12-month calendar is NEVER auto-submitted cover-only - the router HOLDS it
    #     for manual multi-image production. A refactor dropping that branch would
    #     silently under-deliver every calendar post-go-live. (structural, AST: the
    #     calendar-hold branch's 'calendar' + 'multi-image' literals are present.)
    try:
        from quoteforge.fulfillment import router
        impl = router._route_order_impl
        ok = _uses_string(impl, "calendar") and _uses_string(impl, "multi-image")
        checks.append(_c("calendar_multiimage_hold", ok,
                         "router holds calendars for manual multi-image production"
                         if ok else "calendar cover-only-submission hold guard missing"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("calendar_multiimage_hold", False, str(exc)))

    # 28) Branded items (bottle/tumbler/...) have their OWN Gelato placeholder guard
    #     (verify_branded_mappings) so a GEL-* branded SKU can't reach production, and
    #     the cylinder spin recognises them - both were un-invarianted. (behavioral: the
    #     branded verifier runs; structural: _route_order_impl blocks GEL- for all SKUs.)
    try:
        from quoteforge.etsy.branded_catalog import verify_branded_mappings
        from quoteforge.fulfillment import router
        m = verify_branded_mappings()
        ok = (isinstance(m, dict) and "placeholder_count" in m and "all_real" in m
              and _uses_string(router._route_order_impl, "GEL-"))
        checks.append(_c("branded_uid_integrity", ok,
                         f"branded UID guard live (placeholders={m.get('placeholder_count')})"
                         if ok else "branded UID guard not wired"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("branded_uid_integrity", False, str(exc)))

    # 29) Apparel multi-area printing (back + sleeves) never loses money AND actually
    #     prints every area: each extra area's upcharge clears the shop margin +
    #     EXTRA_PRINT_MARGIN_PCT AFTER marketplace fees, and the submission sends a file
    #     per area. (behavioral: priced net margin >= target; structural: create order
    #     carries extra_files + builds the multi-file payload.)
    try:
        from quoteforge.etsy.apparel_print_costs import margin_breakdown
        from quoteforge.config import TARGET_MARGIN_PCT, EXTRA_PRINT_MARGIN_PCT
        from quoteforge.automation import gelato_api
        target = float(TARGET_MARGIN_PCT) + float(EXTRA_PRINT_MARGIN_PCT)
        priced_ok = all(margin_breakdown(a)["margin_pct"] >= target - 0.5
                        for a in ("back", "sleeve-left", "sleeve-right"))
        submit_ok = (_references(gelato_api.create_gelato_order, "extra_files")
                     and _uses_string(gelato_api._build_files, "default"))
        # The router MUST hold a back/sleeve order that lacks per-area files (never
        # silently print front-only) - this safety is unconditional.
        from quoteforge.fulfillment import router
        safety_ok = _references(router._route_order_impl, "_has_extra_print_area")
        ok = priced_ok and submit_ok and safety_ok
        checks.append(_c("apparel_multiarea_profitable", ok,
                         f"extra areas clear {target:.0f}% net + submit per-area files + "
                         "back/sleeve held when files missing"
                         if ok else "multi-area pricing/submission/safety-hold gap"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("apparel_multiarea_profitable", False, str(exc)))

    # 30) The daily Gelato cost/availability discovery agent is wired + GROUNDED: it pulls
    #     REAL prices + discontinued status from the LIVE Gelato API (never a fabricated
    #     number - TEST_MODE/no-key returns a mock with zero costs), reprices to the
    #     margin floor + disables discontinued items + surfaces unmapped/placeholder UIDs,
    #     and runs nightly. This is the no-hallucination cost capture. (behavioral:
    #     sync_catalog runs + returns the grounded shape; structural: it hits the real
    #     gelatoapis endpoint; scheduled: a daily gelato-sync job exists.)
    try:
        from quoteforge.automation.gelato_sync import sync_catalog, _fetch_one
        from quoteforge.automation.scheduler import SCHEDULED_JOBS
        r = sync_catalog()
        grounded = isinstance(r, dict) and "checked" in r and "discontinued" in r
        hits_api = _uses_string(_fetch_one, "product.gelatoapis.com")
        scheduled = any(j.admin_args.startswith("gelato-sync") for j in SCHEDULED_JOBS)
        ok = bool(grounded and hits_api and scheduled)
        checks.append(_c("gelato_cost_sync_grounded", ok,
                         f"daily live Gelato cost/discontinued/UID sync wired + grounded "
                         f"({r.get('checked')} SKUs checked)"
                         if ok else "Gelato cost sync not wired/grounded/scheduled"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("gelato_cost_sync_grounded", False, str(exc)))

    # 31) Shipping shortfall is caught at ORDER time: when shipping is charged separately
    #     (not baked into the price), an order that collected LESS shipping than our cost
    #     is flagged immediately - so a mis-set Etsy shipping profile can't quietly lose
    #     money on every order. (behavioral: a $0-collected apparel order raises a review,
    #     or the check is correctly skipped when FREE_SHIPPING_BAKED is on.)
    try:
        from quoteforge.automation.order_monitor import audit_order
        from quoteforge.config import FREE_SHIPPING_BAKED
        r = audit_order({"order_id": "SHIPCHK", "status": "shipped", "proof_approved": 1,
                         "vendor_order_id": "V", "product_type": "apparel",
                         "shipping_collected": 0.0, "quantity": 1})
        flagged = any("shipping collected" in x for x in r.get("review", []))
        ok = bool(flagged or FREE_SHIPPING_BAKED)
        checks.append(_c("shipping_shortfall_flagged", ok,
                         "order-time guard flags an under-collected shipping order"
                         if ok else "shipping shortfall not caught at order time"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("shipping_shortfall_flagged", False, str(exc)))

    # 32) Sleeve order integrity + single-source compositing (from the sleeve-subsystem
    #     audit): a designed sleeve is previewed AND priced (upcharge), so its CONTENT must
    #     ride in the order payload, and EVERY front-facing render (live proof, spin flip,
    #     basket thumbnail, submitted checkout proof) must go through the ONE
    #     front-with-sleeves compositor - else a paid sleeve ships blank, or the approved
    #     proof doesn't match production. (structural: the generator SOURCE carries the
    #     exact tokens; a comment mention would not satisfy them.)
    try:
        from quoteforge.etsy import listing_preview as _lp
        _src = inspect.getsource(_lp)
        _markers = {
            "order payload carries left sleeve": "'sleeve-left':_stripPhoto(SIDES['sleeve-left'])",
            "order payload carries right sleeve": "'sleeve-right':_stripPhoto(SIDES['sleeve-right'])",
            "one front+sleeves compositor": "function _composedFrontURL(maxDim)",
            "basket thumbnail uses it": "_composedFrontURL(240)",
            "checkout proof uses it": "proof:(IS_APPAREL?_composedFrontURL()",
        }
        _missing = [k for k, tok in _markers.items() if tok not in _src]
        ok = not _missing
        checks.append(_c("sleeve_order_integrity_grounded", ok,
                         "sleeve content rides the order payload + one compositor feeds "
                         "proof/spin/thumbnail/checkout"
                         if ok else f"sleeve integrity regressed: {_missing}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("sleeve_order_integrity_grounded", False, str(exc)))

    # 33) Preview-vs-print safety for apparel: the storefront design is not yet rendered
    #     into the print file (the pipeline substitutes a poster), so an apparel order with
    #     no faithful print file must be HELD for manual, never auto-submitting a poster in
    #     place of the buyer's approved design. (behavioral: route a designed apparel order
    #     with a poster URL and confirm the router returns 'manual', not a submission.)
    try:
        from quoteforge.fulfillment.router import _route_order_impl
        rec = {"name": "Q", "address1": "1 St", "city": "NYC", "state": "NY",
               "postal_code": "10001", "country": "US"}
        import quoteforge.config as _cfg
        _prev_mode = getattr(_cfg, "GELATO_FULFILLMENT_MODE", "native")
        try:
            _cfg.GELATO_FULFILLMENT_MODE = "api"   # force the submit path (not native pull)
            r = _route_order_impl({"order_id": "", "product_type": "apparel",
                                   "vendor": "gelato", "gelato_product_uid": "uid-x"},
                                  recipient=rec, artwork_url="https://x/y.png")
        finally:
            _cfg.GELATO_FULFILLMENT_MODE = _prev_mode
        held = r.get("status") == "manual" and "faithful" in r.get("detail", "")
        checks.append(_c("apparel_preview_matches_print_guard", held,
                         "apparel without a faithful print file is held for manual "
                         "(no poster auto-submitted in place of the approved design)"
                         if held else "apparel would auto-submit a non-faithful poster print"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("apparel_preview_matches_print_guard", False, str(exc)))

    # 34) The DAILY product-photo (mockup) update is wired end to end so the real Gelato
    #     product pictures actually refresh every day and the job can't silently fall out
    #     of the schedule: a daily `mockup-sync` job exists, its command maps to a real
    #     admin handler, it runs BEFORE the 01:50 site rebuild (so fresh confirmed photos
    #     are what publishes), and the rebuild consumes live_mockups(). Without this, a
    #     product (e.g. a tumbler) shows the generated fallback forever even after go-live.
    #     (scheduled + structural; no network / no side effects.)
    try:
        from quoteforge.automation.scheduler import SCHEDULED_JOBS
        from quoteforge.admin import COMMANDS as _CMDS
        from quoteforge.etsy import listing_preview as _lp3
        _msjobs = [j for j in SCHEDULED_JOBS if j.admin_args.startswith("mockup-sync")]
        scheduled = bool(_msjobs)
        wired = "mockup-sync" in _CMDS
        # runs before the daily rebuild so the fresh photos are what gets published
        def _hhmm(j):
            """The job's daily /ST start time (HH:MM), or a late sentinel if none."""
            f = j.schtasks_flags
            return f[f.index("/ST") + 1] if "/ST" in f else "99:99"
        _reb = [j for j in SCHEDULED_JOBS if j.admin_args.startswith("rebuild-site")]
        before_rebuild = bool(_msjobs and _reb and _hhmm(_msjobs[0]) < _hhmm(_reb[0]))
        consumed = "live_mockups" in inspect.getsource(_lp3)   # the rebuild reads confirmed mockups
        ok = bool(scheduled and wired and before_rebuild and consumed)
        checks.append(_c("daily_mockup_update_scheduled", ok,
                         "daily product-photo sync scheduled + wired + runs before the "
                         "rebuild + consumed by the storefront"
                         if ok else "daily product-photo (mockup) update not fully wired: "
                         f"scheduled={scheduled} wired={wired} before_rebuild={before_rebuild} "
                         f"consumed={consumed}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("daily_mockup_update_scheduled", False, str(exc)))

    # 35) The Etsy listing-IMAGE pipeline stays wired end to end: listing_pack GENERATES
    #     its full owner-side gallery set (hero, closeup, size chart, how-it-works,
    #     what's-included - images 3-6 of the best-practice six; the two "official" shots
    #     come from Gelato's native Etsy connector) AND VALIDATES each one non-blank, and
    #     the publisher UPLOADS them RANKED under Etsy's 10-image cap. Without this a
    #     refactor could drop a gallery image or the rank/cap and quietly ship a weak,
    #     conversion-killing gallery. (structural: build_listing_pack references every
    #     generator + the non-blank validator; publish uploads ranked with the 10-cap.)
    try:
        from quoteforge.images import listing_pack as _lp5
        from quoteforge.automation import etsy_publisher as _ep5
        _generators = ("hero_room", "closeup", "size_chart",
                       "how_it_works", "whats_included")
        _gens_wired = all(_references(_lp5.build_listing_pack, g) for g in _generators)
        _validated = _references(_lp5.build_listing_pack, "_check_image")
        _ranked = (_references(_ep5.publish_launch_kit, "upload_image")
                   and _references(_ep5.publish_launch_kit, "rank")
                   and _references(_ep5.publish_launch_kit, "enumerate"))
        _capped = _has_constant(_ep5.publish_launch_kit, 10)   # imgs[:10] Etsy cap
        ok = bool(_gens_wired and _validated and _ranked and _capped)
        checks.append(_c("listing_image_pipeline_wired", ok,
                         "listing gallery generates all 5 owner-side images + validates "
                         "non-blank + uploads ranked under the 10-image cap"
                         if ok else "listing-image pipeline regressed: "
                         f"gens={_gens_wired} validated={_validated} "
                         f"ranked={_ranked} capped={_capped}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("listing_image_pipeline_wired", False, str(exc)))

    # 36) The official-product-image AUTO-PULL is wired end to end so it needs no manual
    #     handoff: a daily `ecommerce-images` job exists + maps to a real admin handler,
    #     and `status()` is a working self-diagnosing probe (returns the enabled/mapped
    #     shape). It is a SAFE no-op until live (TEST_MODE / no store id), and auto-
    #     activates the moment the owner creates the first store product - the real
    #     product photo then appears with zero further wiring. (scheduled + structural.)
    try:
        from quoteforge.automation.scheduler import SCHEDULED_JOBS
        from quoteforge.admin import COMMANDS as _CMDS2
        from quoteforge.automation import ecommerce_images as _ei6
        scheduled = any(j.admin_args.startswith("ecommerce-images") for j in SCHEDULED_JOBS)
        wired = "ecommerce-images" in _CMDS2
        st = _ei6.status()   # never raises; no network in TEST_MODE (gate returns first)
        diagnosable = isinstance(st, dict) and "enabled" in st and "mapped" in st
        # Money-bug guard: the SKU join must SKIP an ambiguous product (return None) and
        # only map a confident key - so it can never put product A's photo on product B.
        safe_join = (_ei6._sku_for({"variants": [{"productUid": "unknown-uid"}]}, {}) is None
                     and _ei6._sku_for({"externalId": "GEL-X"}, {}) == "GEL-X")
        ok = bool(scheduled and wired and diagnosable and safe_join)
        checks.append(_c("ecommerce_image_sync_wired", ok,
                         "daily official-image auto-pull scheduled + wired + self-diagnosing "
                         "+ SKU join skips ambiguous products"
                         if ok else "ecommerce image auto-pull not wired/safe: "
                         f"scheduled={scheduled} wired={wired} diagnosable={diagnosable} "
                         f"safe_join={safe_join}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("ecommerce_image_sync_wired", False, str(exc)))

    # 37) The template-image sync (#181) is wired + persists safely: a daily
    #     `template-sync` job exists + maps to a real handler, the engine is a safe
    #     no-op until live (returns the {enabled, failed} shape without raising), the
    #     DB upsert is IDEMPOTENT (a double-upsert of the same SKU+UID+rank yields ONE
    #     row, never a duplicate image), and the SKU join skips ambiguous products.
    #     (scheduled + behavioral against an ISOLATED temp DB - never touches live data.)
    try:
        from quoteforge.automation.scheduler import SCHEDULED_JOBS
        from quoteforge.admin import COMMANDS as _CMDS3
        from quoteforge.automation import template_image_sync as _ts
        from quoteforge.automation import ecommerce_images as _ei7
        scheduled = any(j.admin_args.startswith("template-sync") for j in SCHEDULED_JOBS)
        wired = "template-sync" in _CMDS3
        r = _ts.sync_template_images()   # TEST_MODE -> no-op, never raises
        diagnosable = (isinstance(r, dict) and "enabled" in r and "failed" in r
                       and r["enabled"] is False)
        safe_join = (_ei7._sku_for({"variants": [{"productUid": "unknown-uid"}]}, {}) is None
                     and _ei7._sku_for({"externalId": "GEL-X"}, {}) == "GEL-X")
        # Idempotency proven behaviorally against an ISOLATED temp DB.
        import tempfile
        from pathlib import Path as _P
        from quoteforge.db import database as _db
        _orig = _db.DB_PATH
        _tmp = _P(tempfile.gettempdir()) / f"qf_infra_tplimg_{os.getpid()}.db"
        try:
            if _tmp.exists():
                _tmp.unlink()
            _db.DB_PATH = _tmp
            _db.init_db()
            _db.upsert_product_image("SKU-A", "https://x/1.png", gelato_product_uid="U1", image_rank=0)
            _db.upsert_product_image("SKU-A", "https://x/2.png", gelato_product_uid="U1", image_rank=0)
            _rows = _db.get_product_images("SKU-A")
            idempotent = len(_rows) == 1 and _rows[0]["image_url"] == "https://x/2.png"
        finally:
            _db.DB_PATH = _orig
            try:
                _tmp.unlink()
            except OSError as _exc:
                logger.debug("infra tpl-img temp cleanup skipped: %s", _exc)
        ok = bool(scheduled and wired and diagnosable and safe_join and idempotent)
        checks.append(_c("template_image_sync_wired", ok,
                         "daily template-image sync scheduled + wired + safe no-op + "
                         "idempotent upsert + SKU join skips ambiguous products"
                         if ok else "template-image sync not wired/safe: "
                         f"scheduled={scheduled} wired={wired} diagnosable={diagnosable} "
                         f"safe_join={safe_join} idempotent={idempotent}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("template_image_sync_wired", False, str(exc)))

    # 38) Etsy listing-create is IDEMPOTENT (from the deployment review, #182): the
    #     create path consults the persisted SKU->listing map before POSTing, so a
    #     re-run (e.g. publish-launch --live twice) can't create duplicate listings.
    #     (structural: create_draft_listing references existing_listing_id + the DB
    #     helper exists + is behaviorally correct against an isolated temp DB.)
    try:
        from quoteforge.automation import etsy_publisher as _ep8
        from quoteforge.db import database as _db8
        refs = _references(_ep8.create_draft_listing, "existing_listing_id")
        helper = hasattr(_db8, "existing_listing_id") and callable(_db8.existing_listing_id)
        behaves = False
        if helper:
            import tempfile
            from pathlib import Path as _P8
            _o8 = _db8.DB_PATH
            _t8 = _P8(tempfile.gettempdir()) / f"qf_infra_listdedupe_{os.getpid()}.db"
            try:
                if _t8.exists():
                    _t8.unlink()
                _db8.DB_PATH = _t8
                _db8.init_db()
                _db8.upsert_product({"product_id": "launch-1", "gelato_sku": "launch-1",
                                     "etsy_listing_id": "L1", "template_id": "",
                                     "category": "c", "title": "t", "price_usd": 1.0,
                                     "gelato_cost_usd": 0.2, "product_type": "print",
                                     "size": ""})
                behaves = _db8.existing_listing_id("launch-1") == "L1" \
                    and _db8.existing_listing_id("launch-none") == ""
            finally:
                _db8.DB_PATH = _o8
                try:
                    _t8.unlink()
                except OSError as _e8:
                    logger.debug("infra listdedupe temp cleanup skipped: %s", _e8)
        ok = bool(refs and helper and behaves)
        checks.append(_c("etsy_listing_create_dedupe", ok,
                         "listing-create checks the SKU->listing map before POST "
                         "(a re-run reuses, never duplicates)"
                         if ok else "listing-create has NO dedupe - re-run duplicates "
                         f"listings: refs={refs} helper={helper} behaves={behaves}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("etsy_listing_create_dedupe", False, str(exc)))

    # 39) The daily image-sync jobs SURFACE failures (from the review, #182): a
    #     silently-failing sync (e.g. store products present but 0 map to a SKU, so the
    #     official image never attaches) must ALERT the owner, not vanish into a log.
    #     (structural: the ecommerce-images + template-sync admin commands reference
    #     the _alert path.)
    try:
        import inspect as _insp9
        from quoteforge import admin as _adm9
        _cmds = {"ecommerce-images": "_cmd_ecommerce_images",
                 "template-sync": "_cmd_template_sync"}
        _missing = [name for name, fn in _cmds.items()
                    if "_alert" not in _insp9.getsource(getattr(_adm9, fn))]
        ok = not _missing
        checks.append(_c("sync_jobs_alert_on_failure", ok,
                         "the daily image-sync commands alert the owner on failure"
                         if ok else f"sync jobs fail silently (no _alert): {_missing}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("sync_jobs_alert_on_failure", False, str(exc)))

    # 40) UPTIME heartbeat wired (#182): each daily automation job stamps a sync_runs
    #     row when it runs, so a job that SILENTLY STOPPED (or whose last run failed) is
    #     detectable. Grounded: the record/read mechanism works (behavioral, isolated
    #     temp DB), the sync admin commands call record_sync_run, and any recorded
    #     last-run for a job is ok (a failing job flags red). The prod RECENCY alert
    #     ("ran <36h ago") lives in healthcheck; this guards the mechanism + health.
    try:
        import inspect as _insp10
        from quoteforge import admin as _adm10
        from quoteforge.db import database as _db10
        recorders = all("record_sync_run" in _insp10.getsource(getattr(_adm10, fn))
                        for fn in ("_cmd_ecommerce_images", "_cmd_template_sync",
                                   "_cmd_mockup_sync"))
        has_api = (hasattr(_db10, "record_sync_run") and hasattr(_db10, "last_sync_run"))
        works = False
        if has_api:
            import tempfile
            from pathlib import Path as _P10
            _o10 = _db10.DB_PATH
            _t10 = _P10(tempfile.gettempdir()) / f"qf_infra_syncruns_{os.getpid()}.db"
            try:
                if _t10.exists():
                    _t10.unlink()
                _db10.DB_PATH = _t10
                _db10.init_db()
                assert _db10.last_sync_run("job-x") == {}          # never ran -> empty
                _db10.record_sync_run("job-x", ok=True, detail="d")
                works = _db10.last_sync_run("job-x").get("ok") == 1
            finally:
                _db10.DB_PATH = _o10
                try:
                    _t10.unlink()
                except OSError as _e10:
                    logger.debug("infra syncruns temp cleanup skipped: %s", _e10)
        ok = bool(recorders and has_api and works)
        checks.append(_c("sync_heartbeat_wired", ok,
                         "each daily job stamps sync_runs (uptime) + the record/read "
                         "mechanism works"
                         if ok else "uptime heartbeat not wired: "
                         f"recorders={recorders} has_api={has_api} works={works}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("sync_heartbeat_wired", False, str(exc)))

    # 41) Listing auto-link closed loop (#182-P0b): the dedupe invariant (#38) only
    #     guards the READ side (create_draft_listing consults existing_listing_id).
    #     This guards the WRITE side: create_draft_listing must PERSIST the new
    #     listing id via upsert_product, or the map never fills and a re-run
    #     duplicates. Plus an orphan detector so a mapped-but-never-published product
    #     (sellable but unbuyable) is visible. Grounded: structural ref + the
    #     orphan_products detector behaves against an isolated temp DB.
    try:
        from quoteforge.automation import etsy_publisher as _ep11
        from quoteforge.db import database as _db11
        writes = _references(_ep11.create_draft_listing, "upsert_product")
        detector = hasattr(_db11, "orphan_products") and callable(_db11.orphan_products)
        behaves = False
        if detector:
            import tempfile
            from pathlib import Path as _P11
            _o11 = _db11.DB_PATH
            _t11 = _P11(tempfile.gettempdir()) / f"qf_infra_orphan_{os.getpid()}.db"
            try:
                if _t11.exists():
                    _t11.unlink()
                _db11.DB_PATH = _t11
                _db11.init_db()
                _base = {"category": "c", "title": "t", "price_usd": 1.0,
                         "gelato_cost_usd": 0.2, "product_type": "print",
                         "size": "", "template_id": ""}
                _db11.upsert_product({**_base, "product_id": "linked",
                                      "gelato_sku": "sku-linked",
                                      "etsy_listing_id": "L9"})        # published
                _db11.upsert_product({**_base, "product_id": "orphan",
                                      "gelato_sku": "sku-orphan",
                                      "etsy_listing_id": ""})          # never published
                orphans = {o["product_id"] for o in _db11.orphan_products()}
                behaves = orphans == {"orphan"}                       # exactly the unlinked one
            finally:
                _db11.DB_PATH = _o11
                try:
                    _t11.unlink()
                except OSError as _e11:
                    logger.debug("infra orphan temp cleanup skipped: %s", _e11)
        ok = bool(writes and detector and behaves)
        checks.append(_c("listing_autolink_wired", ok,
                         "create_draft_listing persists the SKU->listing link + an "
                         "orphan detector surfaces never-published products"
                         if ok else "listing auto-link loop broken: "
                         f"writes={writes} detector={detector} behaves={behaves}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("listing_autolink_wired", False, str(exc)))

    # 42) Audit trail wired (#182-P2): a PRIVILEGED override of a customer-approved
    #     order lock must leave an accountable record (the update_order docstring
    #     promises an "audited admin override"). Grounded: update_order references
    #     record_security_event, AND behaviorally an allow_locked override of an
    #     approved order writes a security_events row (isolated temp DB).
    try:
        from quoteforge.db import database as _db12
        refs = _references(_db12.update_order, "record_security_event")
        has_api = all(hasattr(_db12, n) for n in
                      ("record_security_event", "recent_security_events"))
        behaves = False
        if has_api:
            import tempfile
            from pathlib import Path as _P12
            _o12 = _db12.DB_PATH
            _t12 = _P12(tempfile.gettempdir()) / f"qf_infra_audit_{os.getpid()}.db"
            try:
                if _t12.exists():
                    _t12.unlink()
                _db12.DB_PATH = _t12
                _db12.init_db()
                _oid = _db12.create_order({"order_id": "AUDIT-1",
                                           "recipient_name": "A", "occasion": "B"})
                _db12.update_order(_oid, proof_approved=1)          # lock the order
                _db12.update_order(_oid, occasion="CHANGED",
                                   allow_locked=True)              # audited override
                evs = _db12.recent_security_events(event="order_lock_override")
                behaves = any(_oid in (e.get("detail") or "") for e in evs)
            finally:
                _db12.DB_PATH = _o12
                try:
                    _t12.unlink()
                except OSError as _e12:
                    logger.debug("infra audit temp cleanup skipped: %s", _e12)
        ok = bool(refs and has_api and behaves)
        checks.append(_c("audit_log_wired", ok,
                         "privileged order-lock overrides are recorded to the audit "
                         "trail (accountable)"
                         if ok else "audit trail NOT wired: a privileged override "
                         f"leaves no record: refs={refs} has_api={has_api} behaves={behaves}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("audit_log_wired", False, str(exc)))

    # 43) UTC/local datetime hygiene (recurring bug class, #182 audit): a naive
    #     datetime.now() (LOCAL) compared against a SQLite datetime('now') (UTC)
    #     column is a silent, time-of-day-dependent break. It bit us twice - the
    #     sync-freshness age (healthcheck) and the template stale-sweep (which
    #     RETIRED freshly-written rows). Both now compare in UTC. This tripwire pins
    #     that they STAY UTC-aware: a refactor back to naive-local drops the .utc
    #     reference and flips this red. (Grounded via AST, not a comment/substring.)
    try:
        from quoteforge.automation import healthcheck as _hc13
        from quoteforge.automation import template_image_sync as _tis13
        fresh_utc = _references(_hc13.check_sync_freshness, "utc")
        sweep_utc = _references(_tis13.sync_template_images, "utc")
        ok = bool(fresh_utc and sweep_utc)
        checks.append(_c("utc_local_datetime_hygiene", ok,
                         "the two UTC-vs-local sites that bit us stay UTC-aware "
                         "(sync-freshness + template stale-sweep)"
                         if ok else "REGRESSION - a UTC/local comparator went naive-local: "
                         f"fresh_utc={fresh_utc} sweep_utc={sweep_utc}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("utc_local_datetime_hygiene", False, str(exc)))

    # 44) ALL FOUR route_order callers must thread product_type (#167 audit): route_order
    #     reads product_type ONLY from its arg dict (never the DB), so ANY caller that
    #     omits it silently no-ops the apparel/calendar/calibration holds - e.g. a calendar
    #     reprint auto-submits COVER-ONLY, or front-only apparel auto-submits a poster. The
    #     two orchestrator paths AND the claim-reprint AND the retry path must all pass it.
    #     Grounded per site + a behavioral proof that the calendar hold fires with the key.
    try:
        from quoteforge.automation import pipeline_orchestrator as _po13
        from quoteforge.fulfillment import claim_workflow as _cw13
        from quoteforge.automation import fulfillment_retry as _fr13
        from quoteforge.fulfillment.router import _route_order_impl as _impl13
        callers = {
            "auto": _po13.run_full_pipeline,
            "resume": _po13.resume_after_proof_approval,
            "reprint": _cw13.create_replacement_order,
            "retry": _fr13.retry_failed_fulfillments,
        }
        missing = [n for n, fn in callers.items()
                   if not (_references(fn, "route_order") and _uses_string(fn, "product_type"))]
        # behavioral: a calendar dict carrying product_type MUST hold to manual (never submit)
        held = _impl13({"order_id": "", "product_type": "calendar",
                        "gelato_product_uid": "UID-REAL"},
                       recipient={"a": 1}, artwork_url="https://x/y.png")
        calendar_holds = held.get("status") == "manual"
        ok = bool(not missing and calendar_holds)
        checks.append(_c("route_paths_thread_product_type", ok,
                         "all 4 route_order callers thread product_type; the calendar/"
                         "apparel holds fire on every path (auto/proof/reprint/retry)"
                         if ok else "a route_order caller dropped product_type - a "
                         f"calendar reprint can auto-submit cover-only: missing={missing} "
                         f"calendar_holds={calendar_holds}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("route_paths_thread_product_type", False, str(exc)))

    # 45) Real product-photo override wired (#realphotos). ISSUE: the storefront showed a
    #     drawn silhouette, not the real product, because the only photo source was the
    #     Gelato catalog API - which serves NO product images - hard-gated off in
    #     TEST_MODE. Flipping TEST_MODE=false would NOT fix it (still no API images) and
    #     would risk real orders. RESOLUTION: an owner override manifest checked FIRST in
    #     gelato_blank_image (before the gate) shows the real photo per SKU in TEST_MODE,
    #     display-only, re-hosted same-origin. This pins that the override is still wired
    #     (structural) AND behaves (a manifest SKU resolves in TEST_MODE, isolated temp
    #     file, env restored in finally) so the fix can't silently regress.
    try:
        import os as _os45
        import tempfile as _tf45
        from pathlib import Path as _P45
        from quoteforge.images import supplier_mockup as _sm45
        # the override logic lives in the provenance resolver; gelato_blank_image
        # delegates to it (URL-only wrapper), so check where the source actually is.
        refs = _references(_sm45.gelato_blank_image_provenance, "product_photo_overrides")
        has_api = all(hasattr(_sm45, n) for n in
                      ("product_photo_overrides", "apparel_photo_override_keys"))
        behaves = False
        _prev = _os45.environ.get("PRODUCT_IMAGE_OVERRIDES_FILE")
        _t45 = _P45(_tf45.gettempdir()) / f"qf_infra_photo_ovr_{os.getpid()}.csv"
        try:
            _t45.write_text("sku,url\nQF-INFRA-SKU,https://example.test/real.jpg\n",
                            encoding="utf-8")
            _os45.environ["PRODUCT_IMAGE_OVERRIDES_FILE"] = str(_t45)
            # TEST_MODE is on during infra-check, so this proves the override wins the gate
            behaves = _sm45.gelato_blank_image("QF-INFRA-SKU") == "https://example.test/real.jpg"
        finally:
            if _prev is None:
                _os45.environ.pop("PRODUCT_IMAGE_OVERRIDES_FILE", None)
            else:
                _os45.environ["PRODUCT_IMAGE_OVERRIDES_FILE"] = _prev
            try:
                _t45.unlink()
            except OSError as _e45:
                logger.debug("infra photo-ovr temp cleanup skipped: %s", _e45)
        ok = bool(refs and has_api and behaves)
        checks.append(_c("product_photo_override_wired", ok,
                         "owner real-photo override shows the real product per SKU in "
                         "TEST_MODE (display-only, re-hosted same-origin)"
                         if ok else "real-photo override not wired - storefront can't "
                         f"show real product without go-live: refs={refs} api={has_api} behaves={behaves}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("product_photo_override_wired", False, str(exc)))

    # 46) Apparel editor correctness (end-to-end review): a SLEEVELESS garment (tank)
    #     must never offer sleeve print areas/upcharge - that's an unfulfillable order -
    #     and the BACK proof must not reuse the FRONT photo (misleading). Grounded: the
    #     catalog marks the tank sleeveless AND the page generator gates sleeves on
    #     _garmentSleeves() AND no longer falls the back tile back to the front photo.
    try:
        import inspect as _insp46, re as _re46
        from quoteforge.etsy.apparel_catalog import garment_has_sleeves as _ghs
        from quoteforge.etsy import listing_preview as _lp46
        # Comment-immune (I-1): strip JS // comments so a future refactor can't leave the
        # gate token in a doc-comment while removing the executable gate (matches #48/#50).
        _src46 = "\n".join(_re46.sub(r"//.*$", "", _ln)
                           for _ln in _insp46.getsource(_lp46).splitlines())
        tank_sleeveless = (_ghs("tank") is False and _ghs("tshirt") is True)
        sleeve_gated = ("MULTI_AREA && _garmentSleeves()" in _src46
                        and "APPHASSLEEVES" in _src46
                        and "_sl && _sides['sleeve-left']" in _src46)  # upcharge gated too
        back_not_front = 'if _bk else _front}' not in _src46          # #M3: no misleading fallback
        ok = bool(tank_sleeveless and sleeve_gated and back_not_front)
        checks.append(_c("sleeveless_garment_gated", ok,
                         "sleeveless garments hide sleeve areas/upcharge + back proof "
                         "doesn't reuse the front photo"
                         if ok else "apparel editor correctness regressed: "
                         f"tank_sleeveless={tank_sleeveless} sleeve_gated={sleeve_gated} "
                         f"back_not_front={back_not_front}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("sleeveless_garment_gated", False, str(exc)))

    # 47) Event-table retention wired (hygiene): the append-only heartbeat + audit tables
    #     (sync_runs, security_events) get a retention prune in db_maintenance, else they
    #     grow unbounded. Grounded: db_maintenance references prune_event_tables AND the
    #     prune behaves (deletes an old row, keeps a fresh one) against an isolated temp DB.
    try:
        import tempfile as _tf47
        from pathlib import Path as _P47
        from quoteforge.db import database as _db47
        refs = _references(_db47.db_maintenance, "prune_event_tables")
        has_api = hasattr(_db47, "prune_event_tables")
        behaves = False
        if has_api:
            _o47 = _db47.DB_PATH
            _t47 = _P47(_tf47.gettempdir()) / f"qf_infra_prune_{os.getpid()}.db"
            try:
                if _t47.exists():
                    _t47.unlink()
                _db47.DB_PATH = _t47
                _db47.init_db()
                with _db47._conn() as _c47:
                    _c47.execute("INSERT INTO sync_runs (job, ran_at) VALUES "
                                 "('old', datetime('now','-400 days'))")
                    _c47.execute("INSERT INTO sync_runs (job) VALUES ('new')")
                _pr = _db47.prune_event_tables()
                behaves = (_pr.get("sync_runs") == 1
                           and bool(_db47.last_sync_run("new"))
                           and _db47.last_sync_run("old") == {})
            finally:
                _db47.DB_PATH = _o47
                try:
                    _t47.unlink()
                except OSError as _e47:
                    logger.debug("infra prune temp cleanup skipped: %s", _e47)
        ok = bool(refs and has_api and behaves)
        checks.append(_c("event_retention_pruned", ok,
                         "sync_runs/security_events get a retention prune (bounded growth)"
                         if ok else "event-table retention not wired - unbounded growth: "
                         f"refs={refs} has_api={has_api} behaves={behaves}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("event_retention_pruned", False, str(exc)))

    # 48) Mug wrap-ability gated (fulfillability audit): single-panel mugs (handle breaks
    #     the wrap: colour-interior/accent/travel, wraps=False) must NOT be sold the
    #     full-360 "Wraparound" story or shown a full-wrap spin proof - the buyer would
    #     approve a wrap that prints as one panel. Grounded: the catalog has non-wrap mugs
    #     AND the page emits MUG_WRAPS and consumes it (_mugWraps) at the layout + proof.
    try:
        import inspect as _insp48
        import re as _re48
        from quoteforge.etsy.mug_catalog import MUG_CATALOG as _MC48
        from quoteforge.etsy import listing_preview as _lp48
        # Strip JS // comments before the token scan so a future refactor can't leave
        # the gate token in a doc-comment while removing the executable gate (the audit's
        # anti-substring rule; the gate lives in an emitted JS f-string, not a callable).
        _src48 = "\n".join(_re48.sub(r"//.*$", "", _ln)
                           for _ln in _insp48.getsource(_lp48).splitlines())
        has_nonwrap = any(not m.wraps for m in _MC48)
        emitted = "MUG_WRAPS" in _src48 and "_p.wraps" in _src48
        consumed = ("function _mugWraps()" in _src48
                    and "pk==='mug' && !_mugWraps()" in _src48   # EXECUTABLE layout gate
                    and "arc:(handle?(_mw?5.3:1.9):5.6)" in _src48)  # EXECUTABLE proof arc
        ok = bool(has_nonwrap and emitted and consumed)
        checks.append(_c("mug_wrap_ability_gated", ok,
                         "single-panel mugs hide the Wraparound layout + full-wrap proof"
                         if ok else "mug wrap-ability not consumed by the editor - a "
                         f"single-panel mug can be sold a full wrap: nonwrap={has_nonwrap} "
                         f"emitted={emitted} consumed={consumed}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("mug_wrap_ability_gated", False, str(exc)))

    # 49) Framed wall-art sizes sold must all be FULFILLABLE (fulfillability audit): the
    #     editor once derived framed sizes from POSTER sizes (12x16, 24x36) but
    #     build_wallart_map prepares framed Gelato UIDs ONLY from the framed catalog
    #     sizes - so a customer could pay for a framed size with no prepared UID.
    #     Grounded: every framed size build_variations sells is in the framed catalog.
    try:
        from quoteforge.etsy.variations import build_variations as _bv49, _ns as _ns49
        from quoteforge.etsy.gelato_catalog import GELATO_CATALOG as _GC49
        sold = {_ns49(v.size) for v in _bv49() if v.material == "framed"}
        cat = {_ns49(p.size) for p in _GC49 if p.category == "framed"}
        missing = sorted(sold - cat)
        checks.append(_c("framed_sizes_fulfillable", not missing,
                         "every framed size sold has a prepared framed catalog UID"
                         if not missing else f"framed sizes sold with NO prepared UID: {missing}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("framed_sizes_fulfillable", False, str(exc)))

    # 50) Faithful apparel print files wired (#167 Phase 2b): the editor renders per-side
    #     DTG print files - the DESIGN ONLY, transparent, at PRINT resolution - and
    #     captures them with the order. drawArt must suppress the garment (mockup/
    #     silhouette/shadow) in _PRINTMODE, or the print file would carry a picture of a
    #     shirt. Grounded (comment-immune): the generator has the _PRINTMODE guards +
    #     _printFiles + the order payload. Output stays gated by APPAREL_PRINT_CALIBRATED.
    try:
        import inspect as _insp50, re as _re50
        from quoteforge.etsy import listing_preview as _lp50
        _src50 = "\n".join(_re50.sub(r"//.*$", "", _ln)
                           for _ln in _insp50.getsource(_lp50).splitlines())
        renders = ("function _printFiles()" in _src50
                   and "K=3000/Math.max(ow,oh)" in _src50)          # print resolution
        design_only = ("else if(_PRINTMODE)" in _src50              # transparent, no fill
                       and "!_mock && !_PRINTMODE" in _src50         # no shadow
                       and "if(_mock||_PRINTMODE)" in _src50)        # no drawn garment
        captured = ("_uploadPrintFiles" in _src50                # #Phase2c: upload, not cart
                    and "if(IS_APPAREL) _uploadPrintFiles();" in _src50)
        ok = bool(renders and design_only and captured)
        checks.append(_c("apparel_print_files_wired", ok,
                         "apparel renders faithful design-only per-side print files at "
                         "print resolution + captures them with the order"
                         if ok else "faithful apparel print-file render not wired: "
                         f"renders={renders} design_only={design_only} captured={captured}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("apparel_print_files_wired", False, str(exc)))

    # 51) Print-file upload path wired (#167 Phase 2c): the browser uploads the rendered
    #     print files to /print-files, they're saved + attached to the design, and the
    #     pipeline reads them onto the order. Grounded: the DB API + the /print-files
    #     endpoint + the pipeline read exist AND the decoder rejects a non-PNG side
    #     (behavioral - a malformed upload can't reach the print file).
    try:
        from quoteforge.db import database as _db51
        from quoteforge.images.apparel_print_files import save_print_file_datauris as _spf51
        from quoteforge.automation import webhook_server as _ws51, pipeline_orchestrator as _po51
        import inspect as _insp51
        api = all(hasattr(_db51, n) for n in
                  ("set_design_print_files", "design_print_files_for_order"))
        endpoint = '"/print-files"' in _insp51.getsource(_ws51.create_app) \
            if hasattr(_ws51, "create_app") else "/print-files" in _insp51.getsource(_ws51)
        pipe = _references(_po51.run_full_pipeline, "design_print_files_for_order")
        # behavioral: a non-PNG / unknown side is rejected, never saved
        rejects = save_print_file_datauris_safe(_spf51)
        ok = bool(api and endpoint and pipe and rejects)
        checks.append(_c("apparel_print_files_upload_wired", ok,
                         "print files upload to /print-files, attach to the design, and "
                         "the pipeline reads them onto the order (malformed rejected)"
                         if ok else "print-file upload path not wired: "
                         f"api={api} endpoint={endpoint} pipe={pipe} rejects={rejects}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("apparel_print_files_upload_wired", False, str(exc)))

    # 52) UID->SKU reverse join is collision-safe (Gelato->Etsy image audit): if two of
    #     our SKUs share one real Gelato UID, the inversion must SKIP that UID (ambiguous),
    #     never guess a SKU - else a store product's photo lands on the WRONG SKU's tile
    #     (the exact wrong-product-image the sync exists to prevent). Behavioral.
    try:
        from quoteforge.automation.gelato_sync import invert_uid_map as _inv52
        r = _inv52({"SKU-A": "UID-1", "SKU-B": "UID-1", "SKU-C": "UID-2", "SKU-D": "GEL-X"})
        ok = ("UID-1" not in r and r.get("UID-2") == "SKU-C" and "GEL-X" not in r)
        checks.append(_c("uid_reverse_join_collision_safe", ok,
                         "a UID shared by 2 SKUs is skipped (ambiguous); a unique UID "
                         "resolves; a GEL-* placeholder is excluded"
                         if ok else "UID->SKU reverse join is not collision-safe - a "
                         "shared UID could put the wrong product photo on a tile"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("uid_reverse_join_collision_safe", False, str(exc)))

    # 53) The durably-synced official-image table is CONSUMED by the display path, not a
    #     write-only sink (Gelato->Etsy image audit): template-sync persists + stale-retires
    #     images into gelato_product_images, so the display resolver must read it or that
    #     durability/stale-retire guarantee is inert. Grounded structural ref.
    try:
        from quoteforge.images import supplier_mockup as _sm53
        # the persisted-table read lives in the provenance resolver that
        # gelato_blank_image delegates to.
        ok = _references(_sm53.gelato_blank_image_provenance, "get_product_images")
        checks.append(_c("official_image_table_consumed", ok,
                         "gelato_blank_image reads the persisted gelato_product_images table"
                         if ok else "gelato_product_images is written but no display path "
                         "reads it - persisted/stale-retired images are never shown"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("official_image_table_consumed", False, str(exc)))

    # 54) The SKU->URL supplier-image cache is UID-BOUND (Gelato->Etsy image re-audit):
    #     after the owner REMAPS a SKU to a new Gelato UID, gelato_blank_image must return
    #     the NEW uid's image, not a stale cached one - else the storefront shows the OLD
    #     product forever (no self-heal). Behavioral against an isolated temp cache.
    try:
        import tempfile as _tf54
        from pathlib import Path as _P54
        from quoteforge.images import supplier_mockup as _sm54
        from quoteforge.automation import gelato_sync as _gs54, gelato_api as _ga54
        import quoteforge.config as _cfg54
        _cache = _P54(_tf54.gettempdir()) / f"qf_infra_mockcache_{os.getpid()}.json"
        _o_fetch, _o_ov, _o_map = (_sm54._fetch_product_image,
                                   _sm54.product_photo_overrides, _gs54._uid_map)
        _o_test, _o_key, _o_env = (_cfg54.TEST_MODE, _ga54.GELATO_API_KEY,
                                   os.environ.get("GELATO_MOCKUP_CACHE"))
        try:
            if _cache.exists():
                _cache.unlink()
            os.environ["GELATO_MOCKUP_CACHE"] = str(_cache)
            _cfg54.TEST_MODE = False
            _ga54.GELATO_API_KEY = "k_infra"
            _sm54.product_photo_overrides = lambda: {}
            _sm54._fetch_product_image = lambda uid: f"http://cdn/{uid}.png"
            _gs54._uid_map = lambda: {"SKU-X": "UID-OLD"}
            first = _sm54.gelato_blank_image("SKU-X")            # caches UID-OLD
            _gs54._uid_map = lambda: {"SKU-X": "UID-NEW"}        # owner REMAPS
            second = _sm54.gelato_blank_image("SKU-X")           # must refetch UID-NEW
            ok = (first == "http://cdn/UID-OLD.png" and second == "http://cdn/UID-NEW.png")
        finally:
            _sm54._fetch_product_image, _sm54.product_photo_overrides = _o_fetch, _o_ov
            _gs54._uid_map, _cfg54.TEST_MODE, _ga54.GELATO_API_KEY = _o_map, _o_test, _o_key
            if _o_env is None:
                os.environ.pop("GELATO_MOCKUP_CACHE", None)
            else:
                os.environ["GELATO_MOCKUP_CACHE"] = _o_env
            try:
                _cache.unlink()
            except OSError as _e54:
                logger.debug("infra mockcache cleanup skipped: %s", _e54)
        checks.append(_c("supplier_image_cache_uid_bound", ok,
                         "gelato_blank_image refetches after a SKU->UID remap (uid-bound cache)"
                         if ok else "supplier-image cache is SKU-keyed only - a UID remap keeps "
                         "showing the OLD product's image (no self-heal)"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("supplier_image_cache_uid_bound", False, str(exc)))

    # 55) Variant-UID resolution consults the STATIC uid map BEFORE the dynamic cache
    #     (Gelato->Etsy image re-audit): a stale cached variant UID must never override a
    #     corrected static map entry - that would route an ORDER to the wrong product.
    try:
        import inspect as _insp55
        from quoteforge.automation import gelato_variant_resolver as _gvr55
        src = _insp55.getsource(_gvr55.resolve_variant_uid)
        i_static, i_cache = src.find("_uid_map"), src.find("_load_cache")
        ok = (i_static != -1 and i_cache != -1 and i_static < i_cache)
        checks.append(_c("variant_uid_static_before_cache", ok,
                         "resolve_variant_uid checks the static uid map before the dynamic cache"
                         if ok else "dynamic variant-UID cache can override the static map - a "
                         "stale UID would route an order to the wrong product"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("variant_uid_static_before_cache", False, str(exc)))

    # 56) Apparel image-key linkage, per item, end to end (Gelato->Etsy image-by-UID
    #     re-audit). ISSUE guarded: the tile/editor looks up a garment_id the image
    #     resolver never produces (or a tier variant strips to a base that doesn't
    #     exist) -> that garment silently shows NO real product photo. Behavioral +
    #     grounded: the key the resolver keys by (garment_id, via apparel_sku_for on
    #     sizes[0]) must equal the key the editor looks up (APPGID name->garment_id),
    #     for EVERY garment, and every Value/Premium id must strip (_bgid regex) to a
    #     real Classic base. Fails closed on any missing symbol.
    try:
        import re as _re56
        from quoteforge.etsy.apparel_catalog import (
            APPAREL_CATALOG as _AC56, apparel_sku_for as _ask56,
            parse_apparel_format as _paf56)
        _display56 = {g.garment_id for g in _AC56}
        _resolve56 = {g.garment_id for g in _AC56
                      if g.sizes and g.colors
                      and any(_ask56(g.garment_id, g.sizes[0], c) for c in g.colors)}
        _orphan56 = _display56 - _resolve56          # editor asks, resolver never produces
        _name_bad56 = [g.garment_id for g in _AC56
                       if _paf56(f"{g.name} - {g.colors[0]}")[0] != g.garment_id]
        _bgid_bad56 = [g.garment_id for g in _AC56
                       if _re56.sub(r"_(value|premium)$", "", g.garment_id) not in _display56]
        ok = (not _orphan56 and not _name_bad56 and not _bgid_bad56
              and len(_resolve56) == len(_display56))
        checks.append(_c("apparel_image_key_linkage", ok,
                         f"every apparel garment's image resolve-key == display-key "
                         f"({len(_resolve56)}/{len(_display56)}); tier variants strip to a real base"
                         if ok else "apparel image key drift - a garment/tier would show NO real "
                         f"photo: orphan_display={sorted(_orphan56)} "
                         f"name_collisions={_name_bad56} bgid_no_base={_bgid_bad56}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("apparel_image_key_linkage", False, str(exc)))

    # 57) Every PREPARED framed catalog size must be SELLABLE, or explicitly held
    #     (Gelato->Etsy wall-art per-item re-audit). build_wallart_map prepares a
    #     real framed UID per framed catalog size, but build_variations derives
    #     framed sizes from POSTER sizes - so a framed size with no matching poster
    #     (16x20) gets a UID + price yet NO listing/image/order path. Behavioral: any
    #     framed catalog size that is neither sold NOR in _FRAMED_UNSOLD_OK is an
    #     invisible-product regression (guards a NEW gap; the known 16x20 is held).
    try:
        from quoteforge.etsy.variations import build_variations as _bv57, _ns as _ns57
        from quoteforge.etsy.gelato_catalog import GELATO_CATALOG as _GC57
        _sold57 = {_ns57(v.size) for v in _bv57() if v.material == "framed"}
        _cat57 = {_ns57(p.size) for p in _GC57 if p.category == "framed"}
        _gap57 = sorted(_cat57 - _sold57 - _FRAMED_UNSOLD_OK)
        checks.append(_c("framed_catalog_fully_sellable", not _gap57,
                         "every prepared framed catalog size is sold or explicitly held"
                         if not _gap57 else f"framed catalog sizes with a prepared UID but "
                         f"NO sellable variation and not in _FRAMED_UNSOLD_OK "
                         f"(invisible product): {_gap57}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("framed_catalog_fully_sellable", False, str(exc)))

    # 58) Non-sellable branded items stay QUARANTINED (Gelato->Etsy per-item re-audit):
    #     phonecase is offered in the catalog for future use but has NO per-model UID,
    #     so it must never resolve a routing SKU nor count as sellable - else an order
    #     is taken for an item we cannot fulfil. Behavioral: every id in
    #     NON_SELLABLE_BRANDED resolves branded_sku_for -> None AND branded_sellable
    #     -> False. Fails closed if the quarantine set is emptied or a guard is removed.
    try:
        from quoteforge.etsy.branded_catalog import (
            NON_SELLABLE_BRANDED as _NSB58, branded_sku_for as _bsf58,
            branded_sellable as _bs58)
        # Consistency, not non-emptiness: an empty set is trivially OK (the owner may
        # later promote phonecase once it has per-model UIDs). Anything DECLARED
        # non-sellable must resolve no routing SKU and report not-sellable.
        _leaks58 = [p for p in _NSB58
                    if _bs58(p) or any(_bsf58(p, s, "Black") is not None
                                       for s in ("", "M", "One Size"))]
        ok = not _leaks58
        checks.append(_c("branded_non_sellable_quarantined", ok,
                         f"non-sellable branded items stay quarantined "
                         f"(no routing SKU, not sellable): {sorted(_NSB58)}"
                         if ok else f"a non-sellable branded item is NOT quarantined - it "
                         f"could take an unfulfillable order: leaks={_leaks58} set={sorted(_NSB58)}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("branded_non_sellable_quarantined", False, str(exc)))

    # 59) The infra-check AUDITOR AGENTS are assigned/present. This whole daily agent
    #     GROWS by having the code-outcome-auditor discover new invariants and the
    #     storefront-fulfillability-auditor hunt choose/design/pay-for-unfulfillable
    #     bugs (both feed fixes back here). If an agent .md is deleted or renamed, that
    #     growth loop silently dies. Grounded: on a machine that HAS .claude/agents
    #     (dev/ops), each required auditor file must exist and declare its own name in
    #     frontmatter. Skip-friendly: on a host without .claude (e.g. Render prod) there
    #     is nothing to assign, so it passes rather than false-alarm.
    try:
        import re as _re59
        from pathlib import Path as _Path59
        import quoteforge as _qf59
        _REQUIRED_AUDITOR_AGENTS = ("code-outcome-auditor",
                                    "storefront-fulfillability-auditor",
                                    "gelato-readiness-pilot",
                                    "gelato-uid-verifier")
        _agents_dir = _Path59(_qf59.__file__).resolve().parent.parent / ".claude" / "agents"
        if not _agents_dir.is_dir():
            checks.append(_c("infra_check_auditor_agents_assigned", True,
                             "no .claude/agents on this host (prod) - nothing to assign"))
        else:
            _missing59 = []
            for _name in _REQUIRED_AUDITOR_AGENTS:
                _f = _agents_dir / f"{_name}.md"
                if not _f.is_file():
                    _missing59.append(f"{_name} (file missing)")
                    continue
                _head = _f.read_text(encoding="utf-8", errors="ignore")[:400]
                if not _re59.search(rf"(?m)^\s*name:\s*{_re59.escape(_name)}\s*$", _head):
                    _missing59.append(f"{_name} (name not declared in frontmatter)")
            ok = not _missing59
            checks.append(_c("infra_check_auditor_agents_assigned", ok,
                             f"infra-check auditor agents assigned: "
                             f"{', '.join(_REQUIRED_AUDITOR_AGENTS)}" if ok
                             else f"infra-check auditor agent NOT assigned (growth loop "
                             f"broken): {_missing59}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("infra_check_auditor_agents_assigned", False, str(exc)))

    # 60) The Gelato readiness pipeline is WIRED and its registry does not DRIFT from the
    #     runtime UID map. The registry is the audit entry point; it EXPORTS into the JSON
    #     file gelato_sync._uid_map() reads, so there is one runtime source. Guards:
    #     (a) the engine imports + readiness_report() returns the three gates, (b) the
    #     GEL-* placeholder logic still rejects placeholders, (c) NO verified registry UID
    #     is missing from the runtime map (mapped a UID but forgot to export it - the exact
    #     'two sources of truth' drift to avoid). Pre-go-live both are empty -> consistent.
    try:
        from quoteforge.automation import gelato_readiness as _gr60
        _rep60 = _gr60.readiness_report()
        _has_gates = all(k in _rep60 for k in
                         ("gate1_uid_mapping", "gate2_live_probe", "gate3_calibration",
                          "overall_ready"))
        _placeholder_logic = (_gr60._is_placeholder("GEL-X") is True
                              and _gr60._is_placeholder("real_uid_123") is False)
        _reg60 = _gr60.registry_uid_map()
        _runtime60 = {}
        try:
            from quoteforge.automation.gelato_sync import _uid_map as _um60
            _runtime60 = _um60() or {}
        except Exception as _e60:  # noqa: BLE001
            logger.debug("uid map read skipped in drift check: %s", _e60)
        _drift = sorted(sku for sku, uid in _reg60.items() if _runtime60.get(sku) != uid)
        ok = bool(_has_gates and _placeholder_logic and not _drift)
        checks.append(_c("gelato_readiness_pipeline_wired", ok,
                         "readiness pipeline wired; registry exports cleanly into the "
                         "runtime UID map (no drift)" if ok
                         else f"readiness pipeline issue: gates={_has_gates} "
                         f"placeholder_logic={_placeholder_logic} registry_not_exported={_drift[:5]}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("gelato_readiness_pipeline_wired", False, str(exc)))

    # 61) Apparel print-calibration flag is OWNER-BACKED (Gate 3, hard rule #6). The
    #     router blocks apparel until APPAREL_PRINT_CALIBRATED=true; that flag is only
    #     legitimate once a PHYSICAL test print is owner-approved (a row in
    #     apparel_print_calibration). Catches the dangerous state where the flag was
    #     flipped with NO approval on record -> unverified apparel could print. Flag OFF
    #     (default) is safe (apparel held) -> passes.
    try:
        from quoteforge.config import APPAREL_PRINT_CALIBRATED as _flag61
        from quoteforge.automation.gelato_readiness import calibration_approved as _ca61
        _unbacked = bool(_flag61) and not _ca61("apparel")
        checks.append(_c("apparel_calibration_flag_backed", not _unbacked,
                         "APPAREL_PRINT_CALIBRATED is off (apparel held) or backed by an "
                         "owner physical-print approval" if not _unbacked
                         else "APPAREL_PRINT_CALIBRATED=true with NO owner approval on "
                         "record - unverified apparel could print (hard rule #6)"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("apparel_calibration_flag_backed", False, str(exc)))

    # 62) Gate-1 UID mapping fails CLOSED when the runtime map is UNVERIFIABLE. An
    #     unreadable runtime UID map (e.g. gelato_sync._uid_map raises) must NOT be
    #     reported as "clean" - in live mode that would let Gate 1 false-PASS on the very
    #     map it certifies (unverifiable != safe). Behavioral: feed a runtime map that
    #     RAISES and assert validate_no_gel_placeholders flags it (runtime_read_ok False)
    #     rather than silently ok. Isolated: the monkeypatch is restored in finally.
    try:
        import quoteforge.automation.gelato_sync as _gs62
        from quoteforge.automation import gelato_readiness as _gr62
        _orig62 = _gs62._uid_map

        def _boom62():
            """Decoy runtime-map reader that raises, to prove Gate-1 fails closed."""
            raise RuntimeError("runtime map unreadable")
        _gs62._uid_map = _boom62
        try:
            _v62 = _gr62.validate_no_gel_placeholders()
        finally:
            _gs62._uid_map = _orig62
        _read_ok = _v62.get("runtime_read_ok", True)   # missing key => old swallow
        checks.append(_c("uid_map_unverifiable_fails_closed", _read_ok is False,
                         "runtime UID map read failure is surfaced (runtime_read_ok=False), "
                         "so live Gate-1 cannot PASS on an unverifiable map" if _read_ok is False
                         else "REGRESSION: unreadable runtime UID map is silently treated as "
                         "clean - live Gate-1 could false-PASS"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("uid_map_unverifiable_fails_closed", False, str(exc)))

    # 63) The UID resolver must NEVER auto-write a size-specific apparel SKU from a
    #     SIZE-AGNOSTIC Gelato product. The SKU's own 'GEL-M-' garment code once injected a
    #     phantom 'm' size token, letting a product that names no size clear the confidence
    #     gate and map the WRONG SIZE to a real customer (single-claimant path bypassed the
    #     ambiguity guard). Behavioral: a lone M-size placeholder vs a product carrying only
    #     {apparel,tshirt,white} must be BLOCKED (never resolved).
    try:
        from quoteforge.automation import gelato_uid_resolver as _r63
        _item63 = {"family": "apparel", "sku": "GEL-M-TSHIRT-M-WHITE",
                   "tokens": _r63._sku_tokens("apparel", "GEL-M-TSHIRT-M-WHITE")}
        _prod63 = {"uid": "gel-size-agnostic", "text": "apparel tshirt white", "attrs": {}}
        _res63 = _r63.resolve_sku(_item63, [_prod63])
        _leaked63 = _res63.get("uid") is not None
        checks.append(_c("resolver_size_anchored", not _leaked63,
                         "size-agnostic Gelato product is NOT auto-written to a size-"
                         "specific apparel SKU (size confirmed before write)" if not _leaked63
                         else "REGRESSION: a size-agnostic product maps GEL-M-TSHIRT-M-WHITE "
                         "- wrong garment size could ship to a real customer"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("resolver_size_anchored", False, str(exc)))

    # 64) Automated apparel calibration is CONSENT-GATED and the router consults it. The
    #     vision-QA auto-calibration may open apparel production only with the one-time
    #     AUTO_CALIBRATION_ENABLED consent - so it must be False without consent (behavioral),
    #     and the router's apparel gate must actually call auto_calibration_active
    #     (structural), or a refactor could leave apparel permanently open OR drop the auto-
    #     revert path. Guards the highest-risk zero-owner link.
    try:
        import inspect as _insp64
        from quoteforge.automation import calibration_pipeline as _cp64
        from quoteforge.fulfillment import router as _rt64
        # behavioral: with consent OFF the automated gate is closed regardless of rows
        _consent_off = not _cp64._auto_enabled() and _cp64.auto_calibration_active() is False
        # structural: the router's apparel gate calls the automated gate (the impl the
        # route_order wrapper delegates to)
        _wired = "auto_calibration_active" in _insp64.getsource(_rt64)
        ok = bool(_consent_off and _wired)
        checks.append(_c("auto_calibration_consent_gated", ok,
                         "automated apparel calibration is closed without consent and the "
                         "router consults auto_calibration_active" if ok
                         else f"auto-calibration safety broken: consent_off={_consent_off} "
                         f"router_wired={_wired}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("auto_calibration_consent_gated", False, str(exc)))

    # 65) The apparel auto-calibration AUTO-REVERT tripwire reads the columns disputes
    #     ACTUALLY land in. A post-delivery dispute writes orders.delivery_disputed and a
    #     return/refund claim writes orders.claim_status - NOT orders.status. If the scan
    #     only matched status spellings no producer writes, the owner's primary rail
    #     ("revert on the first dispute") would silently never fire. Behavioral: a real
    #     disputed apparel order in a temp DB must trip _apparel_issue_since.
    try:
        import inspect as _insp65
        import tempfile as _tf65
        import pathlib as _pl65
        from quoteforge.automation import calibration_pipeline as _cp65
        import quoteforge.db.database as _db65
        _src65 = _insp65.getsource(_cp65._apparel_issue_since)
        _cols_ok = ("delivery_disputed" in _src65) and ("claim_status" in _src65)
        _prev65 = _db65.DB_PATH
        _tmp65 = _pl65.Path(_tf65.mkdtemp()) / "cal65.db"
        try:
            _db65.DB_PATH = _tmp65
            _db65.init_db()
            with _db65._conn() as _c65:
                _c65.execute(
                    "INSERT INTO orders (order_id, recipient_name, occasion, product_type, "
                    "status, delivery_disputed, created_at) VALUES "
                    "('T65','A','x','apparel','delivered',1,datetime('now'))")
            _behav_ok = bool(_cp65._apparel_issue_since("1970-01-01"))
        finally:
            _db65.DB_PATH = _prev65
        ok = bool(_cols_ok and _behav_ok)
        checks.append(_c("apparel_revert_reads_dispute_columns", ok,
                         "auto-revert scans delivery_disputed/claim_status and trips on a "
                         "real disputed apparel order" if ok
                         else f"revert tripwire blind to real disputes: cols_ok={_cols_ok} "
                         f"behav_ok={_behav_ok}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("apparel_revert_reads_dispute_columns", False, str(exc)))

    # 66) The automated PHYSICAL test-print order is money-out, so it must stay OFF by
    #     default, cost-capped, idempotent, and route through the SAME idempotent router as
    #     a customer order (never a back-door create). Behavioral: with the consent flag off
    #     it is blocked; structural: the submit routes via route_order and enforces the cap.
    try:
        import inspect as _insp66
        from quoteforge.automation import gelato_live_ops as _lo66
        from quoteforge.config import CALIBRATION_TEST_ORDER_ENABLED as _en66
        _src66 = _insp66.getsource(_lo66.submit_calibration_test_order)
        _routes = ("route_order" in _insp66.getsource(_lo66._route)
                   and "CALIBRATION_TEST_ORDER_MAX_SPEND" in _src66
                   and "_test_order_placed_for" in _src66)
        # behavioral: consent off -> blocked no matter what (default state)
        _blocked_default = True
        if not _en66:
            _r66 = _lo66.submit_calibration_test_order(
                "real_uid", {"name": "A"}, "http://x/a.png", est_cost=15,
                router=lambda o, r, a: {"status": "submitted", "id": "x"})
            _blocked_default = "blocked" in _r66
        ok = bool(_routes and _blocked_default)
        checks.append(_c("test_order_gated_capped_idempotent", ok,
                         "physical test order is consent-gated + capped + idempotent + routes "
                         "through the idempotent router" if ok
                         else f"test-order safety broken: routes={_routes} "
                         f"blocked_default={_blocked_default}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("test_order_gated_capped_idempotent", False, str(exc)))

    # 67) The test-order idempotency guarantee must be DB-ENFORCED, not just a caller-side
    #     COUNT (which is TOCTOU). The router's own dedup is keyed on a persisted orders row
    #     the synthetic calibration order never creates, so a concurrent duplicate must be
    #     refused by a UNIQUE index on an OPEN (pending/test_ordered) productUid - else two
    #     concurrent calls double-order a real garment. Behavioral in an isolated temp DB.
    try:
        import tempfile as _tf67, pathlib as _pl67
        from quoteforge.db import database as _db67
        _prev67 = _db67.DB_PATH
        _tmp67 = _pl67.Path(_tf67.mkdtemp()) / "cal67.db"
        try:
            _db67.DB_PATH = _tmp67
            _db67.init_db()
            with _db67._conn() as _c67:
                _c67.execute("INSERT INTO apparel_print_calibration (product_uid, status) "
                             "VALUES ('U67','test_ordered')")
                _dup_refused = False
                try:
                    _c67.execute("INSERT INTO apparel_print_calibration (product_uid, status) "
                                 "VALUES ('U67','pending')")
                except Exception:  # noqa: BLE001 - the UNIQUE index must refuse this
                    _dup_refused = True
        finally:
            _db67.DB_PATH = _prev67
        checks.append(_c("test_order_uid_unique_backstop", _dup_refused,
                         "an OPEN calibration test order per productUid is UNIQUE-enforced "
                         "at the DB (concurrent double-order impossible)" if _dup_refused
                         else "NO DB uniqueness on apparel_print_calibration.product_uid - "
                         "concurrent duplicate calls could double-order a real garment"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("test_order_uid_unique_backstop", False, str(exc)))

    # 68) An AUTO-resolved UID draft must NEVER reach the runtime map without admin
    #     approval. The resolver only drafts (approved_for_go_live=0); registry_uid_map (the
    #     runtime source) must exclude it until an admin approves. This is the staged go-live
    #     gate - it stops an unverified auto-match from silently going live. Behavioral in an
    #     isolated temp DB: a draft is absent from the map, and present only after approval.
    try:
        import tempfile as _tf68, pathlib as _pl68
        from quoteforge.db import database as _db68
        from quoteforge.automation import gelato_readiness as _gr68
        _prev68 = _db68.DB_PATH
        _tmp68 = _pl68.Path(_tf68.mkdtemp()) / "uid68.db"
        try:
            _db68.DB_PATH = _tmp68
            _db68.init_db()
            _gr68.draft_uid("apparel", "GEL-CHK-68", "real_uid_68", score=0.99, reason="t")
            _absent = "GEL-CHK-68" not in _gr68.registry_uid_map()   # draft NOT live
            _gr68.approve_uid("GEL-CHK-68")
            _present = _gr68.registry_uid_map().get("GEL-CHK-68") == "real_uid_68"
        finally:
            _db68.DB_PATH = _prev68
        ok = bool(_absent and _present)
        checks.append(_c("resolver_draft_needs_approval_to_go_live", ok,
                         "an auto-resolved UID draft is excluded from the runtime map until "
                         "an admin approves it" if ok
                         else f"STAGED GATE BROKEN: draft_absent={_absent} approved_present={_present} "
                         "- an unverified auto-match could go live without approval"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("resolver_draft_needs_approval_to_go_live", False, str(exc)))

    # 69) Automated image validation BLOCKS a bad image and never auto-approves a required
    #     one it can't prove. Replacing user review with automation is only safe if the
    #     validator actually fails closed: a blank/broken image must be BLOCKED, and a rank-1
    #     image must NOT auto-approve without a vision detector confirming the product.
    #     Behavioral, on synthetic images (no live data needed).
    try:
        import io as _io69
        from PIL import Image as _Img69
        from quoteforge.automation import image_validation as _iv69
        _blank = _io69.BytesIO()
        _Img69.new("RGB", (1600, 1600), (255, 255, 255)).save(_blank, "PNG")
        _blocked = _iv69.validate_image_bytes(_blank.getvalue(), family="apparel",
                                              rank=3)["status"] == "BLOCKED"
        _broken = _iv69.validate_image_bytes(b"xx", family="apparel", rank=3)["status"] == "BLOCKED"
        # a real image at rank 1 with NO detector must NOT auto-approve (held for review)
        _content = _io69.BytesIO()
        _im = _Img69.new("RGB", (1600, 1800), (245, 245, 245))
        from PIL import ImageDraw as _Draw69
        _Draw69.Draw(_im).rectangle([300, 300, 1200, 1500], fill=(40, 60, 90))
        _im.save(_content, "PNG")
        _req = _iv69.validate_image_bytes(_content.getvalue(), family="apparel",
                                          rank=1)["status"] != "AUTO_APPROVED"
        ok = bool(_blocked and _broken and _req)
        checks.append(_c("image_validation_fails_closed", ok,
                         "image validator BLOCKS blank/broken images and won't auto-approve a "
                         "required image without product detection" if ok
                         else f"image validator not fail-closed: blank_blocked={_blocked} "
                         f"broken_blocked={_broken} required_held={_req}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("image_validation_fails_closed", False, str(exc)))

    # 70) AUTO_APPROVED (automated validation of the shop's catalog LISTING photos) must stay
    #     SEPARATE from CUSTOMER proof approval. A customer's personalized order can reach
    #     production ONLY via their own affirmative authorization (proof_approved) - the image
    #     validator must NEVER be wired to approve/route/lock an order. Guards both directions:
    #     image_validation references no order/proof/production symbol, AND the customer
    #     affirmative-authorization gate still exists. A refactor that blurs the two -> alert.
    try:
        import inspect as _insp70
        from quoteforge.automation import image_validation as _iv70
        from quoteforge.etsy import listing_preview as _lp70
        _src70 = _insp70.getsource(_iv70)
        _forbidden70 = ("proof_approved", "route_order", "create_order", "resume_after_proof")
        _leaks70 = [t for t in _forbidden70 if t in _src70]
        _consent70 = "I approve this print exactly as shown" in _insp70.getsource(_lp70)
        ok = (not _leaks70) and _consent70
        checks.append(_c("image_validation_separate_from_customer_approval", ok,
                         "automated image validation is separate from customer proof approval "
                         "(no order/proof wiring; the affirmative-authorization gate stands)"
                         if ok else f"SEPARATION BROKEN: image_validation references "
                         f"{_leaks70} / customer_consent_present={_consent70}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("image_validation_separate_from_customer_approval", False, str(exc)))

    # 71) The Etsy OAuth connect flow keeps its guard rails: PKCE (S256) + a state/CSRF param
    #     on the auth URL, the code_verifier is NEVER put on the URL, and the token exchange
    #     NEVER returns/leaks the access/refresh tokens (they go only to the 0600 token file).
    #     A refactor that drops PKCE, drops state, or echoes a token would alert. Behavioral,
    #     isolated temp env; injected poster so no live call.
    try:
        import os as _os71, tempfile as _tf71, pathlib as _pl71, json as _js71
        from quoteforge.automation import etsy_oauth as _oa71
        import quoteforge.config as _cfg71
        _d71 = _pl71.Path(_tf71.mkdtemp())
        _prev = (_os71.environ.get("ETSY_OAUTH_STATE_FILE"), _os71.environ.get("ETSY_TOKEN_FILE"),
                 _cfg71.ETSY_API_KEY, _cfg71.ETSY_OAUTH_REDIRECT_URI, _cfg71.OUTPUT_DIR)
        try:
            _os71.environ["ETSY_OAUTH_STATE_FILE"] = str(_d71 / "st.json")
            _os71.environ["ETSY_TOKEN_FILE"] = str(_d71 / "tok.json")
            _cfg71.ETSY_API_KEY = "k71"; _cfg71.ETSY_OAUTH_REDIRECT_URI = "https://x/cb"
            _cfg71.OUTPUT_DIR = _d71
            _u71 = _oa71.build_auth_url()
            _pkce_ok = (_u71.get("ok") and "code_challenge_method=S256" in _u71["url"]
                        and "state=" in _u71["url"] and "code_verifier" not in _u71["url"])
            _res71 = _oa71.exchange_code("C", state=_u71.get("state", ""),
                                         poster=lambda u, d: {"access_token": "SECRET_AT71",
                                                              "refresh_token": "SECRET_RT71",
                                                              "expires_in": 3600})
            _no_leak = (_res71.get("ok") and "SECRET_AT71" not in _js71.dumps(_res71)
                        and "SECRET_RT71" not in _js71.dumps(_res71))
        finally:
            for _k, _v in (("ETSY_OAUTH_STATE_FILE", _prev[0]), ("ETSY_TOKEN_FILE", _prev[1])):
                if _v is None:
                    _os71.environ.pop(_k, None)
                else:
                    _os71.environ[_k] = _v
            _cfg71.ETSY_API_KEY, _cfg71.ETSY_OAUTH_REDIRECT_URI, _cfg71.OUTPUT_DIR = _prev[2], _prev[3], _prev[4]
        ok = bool(_pkce_ok and _no_leak)
        checks.append(_c("etsy_oauth_pkce_and_no_token_leak", ok,
                         "Etsy connect uses PKCE(S256)+state and the exchange never leaks a "
                         "token" if ok else f"OAuth guard rail broken: pkce_state={_pkce_ok} "
                         f"no_token_leak={_no_leak}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("etsy_oauth_pkce_and_no_token_leak", False, str(exc)))

    # 72) Email quota guard: a customer's transactional email is never dropped because the
    #     shared send quota was burned. TWO properties: (a) _send_email sends NO real email in
    #     TEST_MODE (so tests/dev/CI never consume the quota), and (b) the buyer-facing send
    #     sites are marked critical=True (never deferred by the daily budget). Behavioral +
    #     structural. A regression that lets TEST_MODE send real email, or un-marks a customer
    #     send, would let a real buyer email be dropped.
    try:
        import inspect as _insp72
        import quoteforge.config as _cfg72
        from quoteforge.automation import emailer as _em72
        _prev_tm = _cfg72.TEST_MODE
        _prev_key = _em72.GMAIL_ADDRESS
        try:
            _cfg72.TEST_MODE = True
            _em72.GMAIL_ADDRESS = "probe@x.com"       # creds present, but TEST_MODE must gate
            _no_send = _em72._send_email("probe", "b", to="x@y.com").get("status") == "skipped"
        finally:
            _cfg72.TEST_MODE = _prev_tm
            _em72.GMAIL_ADDRESS = _prev_key
        _customer_critical = all(
            "critical=True" in _insp72.getsource(_m) for _m in (
                __import__("quoteforge.automation.customer_notify", fromlist=["x"]),
                __import__("quoteforge.automation.pipeline_orchestrator", fromlist=["x"])))
        ok = bool(_no_send and _customer_critical)
        checks.append(_c("email_quota_guarded", ok,
                         "TEST_MODE sends no real email + buyer email is critical (never "
                         "deferred)" if ok else f"email quota guard broken: test_mode_gated="
                         f"{_no_send} customer_critical={_customer_critical}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed (alert)
        checks.append(_c("email_quota_guarded", False, str(exc)))

    # 73) Path A reaches 'published': confirm+publish are wired into COMMANDS AND
    #     scheduled (after mockup-sync, before rebuild), and agent_pending() exists so a
    #     stall is detectable. Without this, mockup-sync leaves products at READY forever
    #     (silent stall) and the two-agent wrong-product guard never publishes anything.
    try:
        from quoteforge.automation import mockup_sync as _ms73
        from quoteforge.automation.scheduler import SCHEDULED_JOBS as _sj73
        from quoteforge.admin import COMMANDS as _cmds73
        _wired = "mockup-confirm" in _cmds73 and "mockup-publish" in _cmds73
        _sched = any(j.admin_args.split()[0] in ("mockup-confirm", "mockup-publish",
                     "mockup-pipeline") for j in _sj73)
        _stall = callable(getattr(_ms73, "agent_pending", None))
        ok = bool(_wired and _sched and _stall)
        checks.append(_c("mockup_confirm_publish_scheduled", ok,
                         "confirm+publish scheduled + stall-detector present (Path A reaches live)"
                         if ok else f"Path A stalls at READY: wired={_wired} scheduled={_sched} "
                         f"stall_detector={_stall}"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed
        checks.append(_c("mockup_confirm_publish_scheduled", False, str(exc)))

    # 74) Provenance is bound in the persisted data: confirm() refuses to confirm a
    #     candidate whose recorded origin UID != the SKU's real UID, so a wrong-origin
    #     image (stale DB row / display-only override / a remap) can NEVER publish.
    #     (behavioral: an isolated catalog with a mismatched origin UID must not reach live.)
    try:
        import tempfile as _tmp74, json as _json74, os as _os74
        from quoteforge.automation import mockup_sync as _ms74
        _f74 = _tmp74.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        _f74.write(_json74.dumps({"version": 1, "products": {"P": {
            "sku": "S", "name": "ProbeP", "status": "ready", "confirmed": False,
            "gelato_uid": "UID_A",
            "candidate": {"src": "assets/x.jpg", "fingerprint": "fp", "resolved_uid": "UID_WRONG"},
            "review": {"verdict": "PASS"}, "match": {"verdict": "MATCH"}}}}))
        _f74.close()
        _pe74, _pru74 = _os74.environ.get("MOCKUP_CATALOG_FILE"), _ms74._real_uid
        try:
            _os74.environ["MOCKUP_CATALOG_FILE"] = _f74.name
            _ms74._real_uid = lambda sku: "UID_A"      # the SKU's genuine real uid
            _ms74.confirm(stamp="__probe__")
            _ms74.publish(stamp="__probe__")
            _served74 = _ms74.live_mockups()
        finally:
            _ms74._real_uid = _pru74
            if _pe74 is None:
                _os74.environ.pop("MOCKUP_CATALOG_FILE", None)
            else:
                _os74.environ["MOCKUP_CATALOG_FILE"] = _pe74
            try:
                _os74.unlink(_f74.name)
            except OSError as _exc74:
                logger.debug("mockup provenance probe cleanup skipped: %s", _exc74)
        ok = (_served74 == {})    # wrong-origin candidate must never reach live_mockups()
        checks.append(_c("mockup_provenance_bound", ok,
                         "confirm() gates on image origin UID == SKU's real UID"
                         if ok else "PROVENANCE HOLE: a wrong-origin image confirmed+published"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed
        checks.append(_c("mockup_provenance_bound", False, str(exc)))

    # 75) A remap invalidates a published photo: live_mockups() serves a live block ONLY
    #     while its bound origin UID still equals the SKU's current real UID. A remapped
    #     SKU drops its stale photo (else the customer keeps seeing the old product).
    #     (behavioral: remapped product excluded, matching product still served.)
    try:
        import tempfile as _tmp75, json as _json75, os as _os75
        from quoteforge.automation import mockup_sync as _ms75
        _f75 = _tmp75.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        _f75.write(_json75.dumps({"version": 1, "products": {
            "STALE": {"sku": "S_STALE", "name": "Stale", "status": "published",
                      "confirmed": True, "gelato_uid": "OLD",
                      "live": {"src": "assets/old.jpg", "resolved_uid": "OLD"}},
            "OK": {"sku": "S_OK", "name": "Fresh", "status": "published",
                   "confirmed": True, "gelato_uid": "CUR",
                   "live": {"src": "assets/cur.jpg", "resolved_uid": "CUR"}}}}))
        _f75.close()
        _pe75, _pru75 = _os75.environ.get("MOCKUP_CATALOG_FILE"), _ms75._real_uid
        try:
            _os75.environ["MOCKUP_CATALOG_FILE"] = _f75.name
            # S_STALE remapped to a NEW uid; S_OK still maps to its bound uid.
            _ms75._real_uid = lambda sku: "CUR" if sku == "S_OK" else "NEW"
            _served75 = _ms75.live_mockups()
        finally:
            _ms75._real_uid = _pru75
            if _pe75 is None:
                _os75.environ.pop("MOCKUP_CATALOG_FILE", None)
            else:
                _os75.environ["MOCKUP_CATALOG_FILE"] = _pe75
            try:
                _os75.unlink(_f75.name)
            except OSError as _exc75:
                logger.debug("mockup remap probe cleanup skipped: %s", _exc75)
        ok = ("Stale" not in _served75) and ("Fresh" in _served75)
        checks.append(_c("mockup_remap_invalidates_live", ok,
                         "a remapped SKU's stale photo is dropped; matching one still serves"
                         if ok else "STALE-UID HOLE: a remapped SKU keeps serving the old product"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed
        checks.append(_c("mockup_remap_invalidates_live", False, str(exc)))

    # 76) Deterministic wrong-product backstop: invert_uid_map() DROPS any UID shared by
    #     >1 SKU (an ambiguous reverse join would land one product's photo on another's
    #     tile) and keeps the unambiguous ones. (behavioral)
    try:
        from quoteforge.automation.gelato_sync import invert_uid_map as _inv76
        _amb = _inv76({"SKU_A": "UID_SHARED", "SKU_B": "UID_SHARED", "SKU_C": "UID_OK"})
        ok = ("UID_SHARED" not in _amb) and (_amb.get("UID_OK") == "SKU_C")
        checks.append(_c("mockup_wrong_family_backstop", ok,
                         "ambiguous shared UID is dropped (no wrong-product reverse join)"
                         if ok else "AMBIGUOUS UID not dropped - wrong-product photo risk"))
    except Exception as exc:  # noqa: BLE001 - missing symbol -> fail closed
        checks.append(_c("mockup_wrong_family_backstop", False, str(exc)))

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def save_print_file_datauris_safe(_spf) -> bool:
    """Behavioral probe for invariant #51: the print-file decoder rejects a non-PNG /
    unknown side and returns {} for a bad email, never raising."""
    try:
        return (_spf("no-at-sign", "d", {"front": "data:image/png;base64,AAAA"}) == {}
                and _spf("a@b.com", "d", {"collar": "x", "front": "data:text/plain,y"}) == {})
    except Exception:  # noqa: BLE001
        return False


# Supplier names that must NEVER appear in a customer surface (mirror of the
# constant the test suite pins in test_customer_copy_no_leak.py).
_SUPPLIER_NAMES = ("gelato", "printify", "printful")


def _supplier_name_leaks() -> list:
    """Return a list of '<surface>:<name>' for any supplier name found in a
    customer-facing source generator or the published storefront. Empty == clean.

    The SOURCE generators are read via inspect (always present); the storefront
    files are best-effort (a not-yet-built page simply can't leak)."""
    from pathlib import Path

    leaks: list[str] = []

    # Customer-facing SOURCE generators: a name here regenerates into the page.
    from quoteforge.etsy import listing_preview, customer_messages
    sources = {"listing_preview.py": listing_preview,
               "customer_messages.py": customer_messages}
    try:
        from quoteforge.ai import ange
        sources["ange.py"] = ange
    except Exception as exc:  # noqa: BLE001 - the storefront assistant is optional
        logger.debug("optional ange import skipped in leak scan: %s", exc)
    for label, mod in sources.items():
        text = inspect.getsource(mod).lower()
        leaks += [f"{label}:{n}" for n in _SUPPLIER_NAMES if n in text]

    # The PUBLISHED storefront (page + externalized JS bundle).
    import quoteforge
    docs = Path(quoteforge.__file__).resolve().parent.parent / "docs"
    page = ""
    for fn in ("index.html", "app.js"):
        p = docs / fn
        if p.exists():
            page += p.read_text(encoding="utf-8").lower()
    leaks += [f"storefront:{n}" for n in _SUPPLIER_NAMES if n in page]

    return leaks
