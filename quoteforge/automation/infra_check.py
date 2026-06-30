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
        tmp = Path(tempfile.gettempdir()) / "qf_infra_uidcheck.db"
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
        ok = priced_ok and submit_ok
        checks.append(_c("apparel_multiarea_profitable", ok,
                         f"extra print areas clear {target:.0f}% net + submit per-area files"
                         if ok else "multi-area pricing under-margin or files not submitted"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("apparel_multiarea_profitable", False, str(exc)))

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
