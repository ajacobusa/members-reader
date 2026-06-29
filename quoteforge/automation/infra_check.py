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
import textwrap


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

    # 14) The fulfillment router surfaces every error (risk #2/#14). A silently
    #     swallowed DB write in the routing path (storing the vendor_order_id, or
    #     the submit_unconfirmed status) defeats the duplicate-submission guard, so
    #     a re-run could double-charge. (behavioral: the real AST smell detector
    #     finds zero silently-swallowed excepts in the router.)
    try:
        from quoteforge.automation.code_auditor import audit_module
        silent = [s for s in audit_module("fulfillment/router.py")["smells"]
                  if s["kind"] == "silent_except"]
        checks.append(_c("router_surfaces_errors", not silent,
                         "fulfillment router never swallows an error"
                         if not silent
                         else f"{len(silent)} silent except in router "
                              f"(dedup guard at risk): lines "
                              f"{[s['line'] for s in silent]}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_c("router_surfaces_errors", False, str(exc)))

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
    except Exception:  # noqa: BLE001 - the storefront assistant is optional
        pass
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
