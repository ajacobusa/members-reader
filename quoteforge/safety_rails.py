"""Safety guardrails — the decisions that must NEVER be automated.

Refunds, cancellations, claim adjudication, margin-floor holds, and address fixes stay
under HUMAN control: automating any of them risks money, wrong prints, and Etsy/Gelato
standing. As the rest of the system runs more hands-free, these invariants must not be
able to drift — so this module makes them explicit and SELF-MONITORING.

  - check_safety_rails() verifies each config-checkable rail still holds.
  - the daily `safety-check` job ALERTS the owner if any rail weakens (e.g. someone sets
    a non-zero auto-refund cap, blanks the margin floor, or wires a claim decision into a
    cron job).
  - test_safety_rails.py locks every rail (incl. the code invariants) so no future change
    can quietly break one.

This is a guardrail, not a gate that blocks the owner: a human can still refund, cancel,
or decide a claim from the admin CLI - the rail only prevents AUTOMATION from doing so.
"""
from __future__ import annotations


def _rail(name: str, ok: bool, detail: str) -> dict:
    """One guardrail result: its name, whether it holds, and a human-readable detail."""
    return {"name": name, "ok": bool(ok), "detail": detail}


def check_safety_rails() -> dict:
    """Verify every config-checkable safety guardrail. Returns {ok, rails:[...]}.
    ok is False if ANY rail has weakened - the daily job alerts on that."""
    rails = []

    # 1) Refunds + spend: no money leaves automatically. The autopilot auto-refund cap
    #    is $0, so every refund is STAGED for a human, never auto-issued.
    from quoteforge.config import (AUTOPILOT_MAX_AUTO_REFUND, MARGIN_FLOOR_ENTRY,
                                   MARGIN_FLOOR_MID, MARGIN_FLOOR_TOP)
    rails.append(_rail(
        "no_auto_refund", float(AUTOPILOT_MAX_AUTO_REFUND or 0) <= 0,
        f"AUTOPILOT_MAX_AUTO_REFUND=${AUTOPILOT_MAX_AUTO_REFUND} "
        "(any value > 0 lets the bot auto-refund up to it - keep it 0)"))

    # 2) Margin-floor holds: the floor is real (>0), so a below-floor order is held for
    #    review instead of auto-sold at a loss.
    floors = (MARGIN_FLOOR_ENTRY, MARGIN_FLOOR_MID, MARGIN_FLOOR_TOP)
    rails.append(_rail(
        "margin_floor_set", all(float(f or 0) > 0 for f in floors),
        "floors entry/mid/top = " + "/".join(str(f) for f in floors)))

    # 3) Order lock: a proof-approved order's design/personalization/size are immutable.
    from quoteforge.db.database import LOCKED_FIELDS
    rails.append(_rail(
        "order_lock_active", len(LOCKED_FIELDS) > 0,
        f"{len(LOCKED_FIELDS)} fields locked after proof_approved"))

    # 4) Claim adjudication is human-only: NO scheduled job runs the claim-decide command
    #    (it lives only in the admin CLI).
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    cron_cmds = {(j.admin_args or "").split()[0] for j in SCHEDULED_JOBS if j.admin_args}
    rails.append(_rail(
        "claims_human_only", "claim-decide" not in cron_cmds,
        "claim-decide is admin-CLI only; no scheduled job adjudicates claims"))

    # 5) Address-fix gate: an incomplete ship-to is HELD as manual, never auto-submitted
    #    to the print partner (return-to-sender protection).
    from quoteforge.fulfillment.gelato_returns import normalize_recipient
    bad = normalize_recipient({"name": "X"})           # missing street/city/postcode/country
    rails.append(_rail(
        "address_fix_required", not bad["valid"],
        "an incomplete address is invalid -> routed to manual, not auto-submitted"))

    # 6) submit_unconfirmed is NEVER auto-retried (an ambiguous send may already have
    #    charged + printed; a blind re-send would double both).
    from quoteforge.automation.fulfillment_retry import _eligible, MAX_RETRIES
    unconf = {"status": "submit_unconfirmed", "vendor_order_id": "",
              "fulfillment_retries": 0}
    rails.append(_rail(
        "unconfirmed_not_auto_retried", not _eligible(unconf, MAX_RETRIES),
        "fulfillment_retry re-drives only confirmed status='error', excludes submit_unconfirmed"))

    return {"ok": all(r["ok"] for r in rails), "rails": rails}
