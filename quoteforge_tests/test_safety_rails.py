"""Safety guardrails - the decisions that must NEVER be automated (refunds,
cancellations, claim adjudication, margin-floor holds, address fixes). These tests LOCK
each invariant so no future change can quietly break one, and prove the guardrail
SELF-MONITORS: a misconfiguration that would weaken a rail is caught + alerted.
"""


def test_all_guardrails_intact_by_default():
    from quoteforge.safety_rails import check_safety_rails
    r = check_safety_rails()
    assert r["ok"] is True
    assert {x["name"] for x in r["rails"]} == {
        "no_auto_refund", "margin_floor_set", "order_lock_active",
        "claims_human_only", "address_fix_required", "unconfirmed_not_auto_retried"}
    assert all(x["ok"] for x in r["rails"])


def test_no_auto_refund_cap_is_zero():
    # REGRESSION: money never leaves automatically.
    from quoteforge.config import AUTOPILOT_MAX_AUTO_REFUND
    assert float(AUTOPILOT_MAX_AUTO_REFUND or 0) == 0


def test_misconfigured_refund_cap_trips_the_guardrail(monkeypatch):
    # The whole point: if someone sets a non-zero auto-refund cap, the guardrail FAILS
    # (so the daily safety-check alerts) instead of silently letting money auto-leave.
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "AUTOPILOT_MAX_AUTO_REFUND", 50.0)
    from quoteforge.safety_rails import check_safety_rails
    r = check_safety_rails()
    rail = next(x for x in r["rails"] if x["name"] == "no_auto_refund")
    assert rail["ok"] is False and r["ok"] is False


def test_claim_adjudication_is_human_only():
    # REGRESSION: claim-decide is admin-CLI only; no scheduled job may adjudicate a claim.
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    cron_cmds = {(j.admin_args or "").split()[0] for j in SCHEDULED_JOBS if j.admin_args}
    assert "claim-decide" not in cron_cmds


def test_submit_unconfirmed_never_auto_retried():
    # REGRESSION: an ambiguous send may already have charged + printed - never re-driven.
    from quoteforge.automation.fulfillment_retry import _eligible, MAX_RETRIES
    assert not _eligible({"status": "submit_unconfirmed", "vendor_order_id": "",
                          "fulfillment_retries": 0}, MAX_RETRIES)


def test_order_lock_and_margin_floor_active():
    from quoteforge.db.database import LOCKED_FIELDS
    from quoteforge.config import MARGIN_FLOOR_ENTRY, MARGIN_FLOOR_MID, MARGIN_FLOOR_TOP
    assert len(LOCKED_FIELDS) > 0
    assert all(float(f or 0) > 0 for f in (MARGIN_FLOOR_ENTRY, MARGIN_FLOOR_MID,
                                           MARGIN_FLOOR_TOP))


def test_incomplete_address_is_held_not_auto_submitted():
    from quoteforge.fulfillment.gelato_returns import normalize_recipient
    assert normalize_recipient({"name": "X"})["valid"] is False   # missing street/city/zip/country


def test_safety_check_command_alerts_when_a_rail_weakens(monkeypatch):
    # The daily job must ALERT (and exit non-zero) the moment a guardrail weakens.
    import quoteforge.config as cfg
    import quoteforge.admin as admin
    monkeypatch.setattr(cfg, "AUTOPILOT_MAX_AUTO_REFUND", 99.0)
    alerts = []
    monkeypatch.setattr(admin, "_alert",
                        lambda subj, body, what=None: alerts.append(subj))
    rc = admin.main(["safety-check"])
    assert rc == 1 and alerts and "GUARDRAIL" in alerts[0]
