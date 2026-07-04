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
        refs = _references(_sm45.gelato_blank_image, "product_photo_overrides")
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
        import inspect as _insp46
        from quoteforge.etsy.apparel_catalog import garment_has_sleeves as _ghs
        from quoteforge.etsy import listing_preview as _lp46
        _src46 = _insp46.getsource(_lp46)
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

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


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
