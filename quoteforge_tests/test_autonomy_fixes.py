"""Autonomy fixes from the infrastructure review (4 confirmed) + the recurring
infra-check agent that re-verifies them:
- CRITICAL: Etsy OAuth token auto-refresh (intake no longer dies ~1h after go-live)
- HIGH: the poller SURFACES failed imports (a paid order never vanishes silently)
- MED: the dispute scan degrades on an API error (doesn't crash the job)
- LOW: approved_ready_to_print is surfaced in the needs-action digest
All network mocked / tmp.
"""
import json
import sqlite3


# ---------------------------------------------------- CRITICAL: OAuth refresh
def test_with_refresh_retries_once_on_401(monkeypatch):
    import requests
    import quoteforge.automation.etsy_auth as auth
    monkeypatch.setattr(auth, "refresh_access_token", lambda: "fresh-token")
    state = {"n": 0}

    def call():
        state["n"] += 1
        if state["n"] == 1:
            e = requests.HTTPError("401")
            e.response = type("R", (), {"status_code": 401})()
            raise e
        return "ok"
    assert auth.with_refresh(call) == "ok" and state["n"] == 2   # refreshed + retried


def test_refresh_access_token_persists_rotated_tokens(tmp_path, monkeypatch):
    import requests
    import quoteforge.config as cfg
    import quoteforge.automation.etsy_auth as auth
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(cfg, "ETSY_API_KEY", "k")
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(tmp_path / "tok.json"))
    monkeypatch.setattr(auth, "current_refresh_token", lambda: "rt")

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "A2", "refresh_token": "R2", "expires_in": 3600}
    monkeypatch.setattr(requests, "post", lambda *a, **k: _R())
    assert auth.refresh_access_token() == "A2"
    saved = json.loads((tmp_path / "tok.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == "A2" and saved["refresh_token"] == "R2"  # rotation persisted
    assert auth.current_access_token() == "A2"


# ---------------------------------------------------------- HIGH: poller surfaces
def test_poller_surfaces_failed_imports(monkeypatch):
    import quoteforge.automation.etsy_api as ea
    import quoteforge.automation.monitoring as mon
    import quoteforge.automation.webhook_server as ws
    monkeypatch.setattr(ea, "get_shop_receipts",
                        lambda **k: {"results": [{"id": 1}, {"id": 2}]})

    def _conv(r):
        if r["id"] == 2:
            raise ValueError("malformed receipt")
        return {"etsy_order_id": "R1", "recipient_name": "X", "occasion": "B"}
    monkeypatch.setattr(ea, "receipt_to_order_payload", _conv)
    monkeypatch.setattr(ws, "process_webhook_payload", lambda p: None)
    monkeypatch.setattr(ws, "_is_duplicate", lambda oid: False)
    captured = []
    monkeypatch.setattr(mon, "capture", lambda e: captured.append(e))
    from quoteforge.automation.etsy_poller import poll_once
    r = poll_once()
    assert r["imported"] == ["R1"] and r["failed"]              # receipt 2 surfaced, not silent
    assert captured                                            # and captured to Sentry


def test_poll_etsy_command_alerts_on_failure(monkeypatch):
    import quoteforge.admin as admin
    import quoteforge.automation.etsy_poller as poller
    monkeypatch.setattr(poller, "poll_once",
                        lambda: {"polled": 1, "imported": [], "skipped": 0,
                                 "failed": ["R9"]})
    alerts = []
    monkeypatch.setattr(admin, "_alert", lambda s, b, what=None: alerts.append(s))
    admin.main(["poll-etsy"])
    assert alerts                                              # owner alerted on a failed import


# ----------------------------------------------------- MED: dispute scan degrades
def test_dispute_scan_degrades_on_api_error(monkeypatch):
    import quoteforge.automation.etsy_api as ea
    monkeypatch.setattr(ea, "_credentials_ready", lambda: True)

    def _boom(**k):
        raise RuntimeError("etsy down")
    monkeypatch.setattr(ea, "get_shop_receipts", _boom)
    from quoteforge.automation.dispute_scanner import scan_etsy_disputes
    r = scan_etsy_disputes()                                   # must NOT raise
    assert r["status"] == "error" and r["disputed"] == []


# --------------------------------------------------- LOW: approved_ready surfaced
def test_approved_ready_to_print_in_needs_attention(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,status) "
                 "VALUES (?,?,?,?)", ("O1", "R", "B", "approved_ready_to_print"))
    conn.commit()
    conn.close()
    rep = db.daily_order_report()
    assert any(o["order_id"] == "O1" for o in rep["needs_attention"])


# ------------------------------------------------- the recurring infra-check agent
def test_infra_check_all_pass():
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    assert r["ok"] is True
    names = {c["name"] for c in r["checks"]}
    assert {"scheduled_jobs_wired", "etsy_oauth_refresh_wired",
            "poller_surfaces_failures", "dispute_scan_guarded",
            "approved_ready_surfaced", "safety_guardrails"} <= names


# REGRESSION: the 6 critical order-lifecycle risks that previously had only a
# build-time test are now DAILY-monitored invariants - the agent must surface all
# of them and they must all hold against the real code.
def test_infra_check_covers_critical_lifecycle_risks():
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    by_name = {c["name"]: c for c in r["checks"]}
    for name in ("no_duplicate_supplier_submission", "delivery_strict_confirm",
                 "review_after_delivery_only", "claim_evidence_required",
                 "shipping_variance_wired", "no_supplier_name_leak"):
        assert name in by_name, f"infra-check no longer monitors {name}"
        assert by_name[name]["ok"], f"{name} regressed: {by_name[name]['detail']}"


def _check(r, name):
    return next(c for c in r["checks"] if c["name"] == name)


# REGRESSION: the fulfillment router must surface every error. A swallowed DB write
# in the routing path (vendor_order_id / submit_unconfirmed) defeats the
# duplicate-submission guard, so a re-run could double-charge.
def test_order_path_modules_have_no_silent_except():
    from quoteforge.automation.code_auditor import audit_module
    for m in ("fulfillment/router.py", "automation/webhook_server.py",
              "automation/pipeline_orchestrator.py"):
        silent = [s["line"] for s in audit_module(m)["smells"]
                  if s["kind"] == "silent_except"]
        assert silent == [], f"silent except(s) in {m} at lines {silent}"


def test_infra_check_guards_order_path_silent_except():
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    assert _check(r, "order_path_surfaces_errors")["ok"] is True


# GROUNDING: prove the invariant CATCHES a re-introduced silent except (it runs the
# real AST detector, so a decoy with a swallowed except must fail it).
def test_infra_check_catches_an_order_path_silent_except(monkeypatch):
    from quoteforge.automation.infra_check import check_infrastructure
    # The check does `from ...code_auditor import audit_module` at call time, so
    # patching the module attribute makes it see the decoy.
    import quoteforge.automation.code_auditor as ca
    monkeypatch.setattr(ca, "audit_module", lambda m, protected=None: {
        "module": m, "smells": [{"kind": "silent_except", "line": 99,
                                 "detail": "swallowed"}],
        "coverage_gaps": [], "public_defs": [], "ok": False})
    r = check_infrastructure()
    assert _check(r, "order_path_surfaces_errors")["ok"] is False and r["ok"] is False


# GROUNDING: prove the AST structural check CATCHES a back-door, and isn't fooled
# by the router name merely appearing in a comment. The decoy calls
# create_gelato_order directly (and only NAMES route_order in a comment).
def test_infra_check_catches_removed_idempotency_guard(monkeypatch):
    import quoteforge.automation.pipeline_orchestrator as po
    from quoteforge.automation.infra_check import check_infrastructure

    def _decoy_resume(order_id, gelato_product_uid="", recipient_address=None):
        # route_order  <- named in a comment; a substring check would be fooled
        from quoteforge.automation.gelato_api import create_gelato_order  # back-door
        return create_gelato_order(order_id=order_id)
    monkeypatch.setattr(po, "resume_after_proof_approval", _decoy_resume)
    r = check_infrastructure()
    assert _check(r, "no_duplicate_supplier_submission")["ok"] is False
    assert r["ok"] is False


# GROUNDING: prove the strict-delivered AST check rejects a SUBSTRING weakening
# ('delivered' in st) that the old `'st == "delivered"' in source` would miss.
def test_infra_check_catches_loosened_delivery_confirm(monkeypatch):
    import quoteforge.automation.fulfillment_tracker as ft
    from quoteforge.automation.infra_check import check_infrastructure

    def _decoy_confirm(order, delivered_confirmed, *a, **k):
        st = order.get("status", "")
        if "delivered" in st:          # LOOSE: also matches 'out_for_delivery'
            delivered_confirmed.append(order["order_id"])
    monkeypatch.setattr(ft, "_carrier_confirm", _decoy_confirm)
    r = check_infrastructure()
    assert _check(r, "delivery_strict_confirm")["ok"] is False
    assert r["ok"] is False


# GROUNDING: prove the behavioral review-timing check CATCHES a removed guard by
# observing real output - a decoy that returns the 'shipped' order must fail it.
def test_infra_check_catches_premature_review(monkeypatch):
    import quoteforge.etsy.delight_loop as dl
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr(dl, "delight_due", lambda orders, *a, **k: list(orders))
    r = check_infrastructure()
    assert _check(r, "review_after_delivery_only")["ok"] is False
    assert r["ok"] is False


def test_infra_check_alerts_on_regression(monkeypatch):
    import quoteforge.admin as admin
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "AUTOPILOT_MAX_AUTO_REFUND", 99.0)   # weaken a guardrail
    alerts = []
    monkeypatch.setattr(admin, "_alert", lambda s, b, what=None: alerts.append(s))
    rc = admin.main(["infra-check"])
    assert rc == 1 and alerts and "INFRASTRUCTURE" in alerts[0]
