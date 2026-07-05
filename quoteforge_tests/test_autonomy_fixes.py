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
    # Every CODE-invariant check must pass. runtime_health probes the LIVE machine
    # (daemons/ports/plugins), which varies per host/CI, so it's asserted only to be
    # PRESENT here and tested deterministically in test_runtime_health.py.
    non_env = [c for c in r["checks"] if c["name"] != "runtime_health"]
    assert all(c["ok"] for c in non_env), [c for c in non_env if not c["ok"]]
    names = {c["name"] for c in r["checks"]}
    assert {"scheduled_jobs_wired", "etsy_oauth_refresh_wired",
            "poller_surfaces_failures", "dispute_scan_guarded",
            "approved_ready_surfaced", "safety_guardrails", "runtime_health"} <= names


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
              "automation/pipeline_orchestrator.py", "db/database.py",
              "automation/order_monitor.py", "automation/autopilot.py",
              "automation/etsy_poller.py", "automation/gelato_api.py",
              "fulfillment/claim_workflow.py", "images/final_qc.py",
              "etsy/subscription_product.py"):
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


# Each MAJOR fix shipped this cycle is now a daily infra-check guard, so the issue
# can't silently return.
def test_infra_check_guards_major_session_fixes():
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    by = {c["name"]: c for c in r["checks"]}
    for name in ("backup_gated_to_main", "guards_automated_in_prod",
                 "no_silent_except_regression", "scans_exclude_worktrees"):
        assert name in by, f"infra-check no longer guards {name}"
        assert by[name]["ok"], f"{name} regressed: {by[name]['detail']}"


def test_infra_check_catches_ungated_backup(monkeypatch):
    # GROUNDING: an auto-backup that lost its branch gate must flip the agent red.
    import quoteforge.automation.full_backup as fb
    from quoteforge.automation.infra_check import check_infrastructure

    def _ungated_backup(push=True, auto_commit=True, runner=None):
        # no 'main' / '--abbrev-ref' branch gate at all
        return {"auto_commit": "committed"}
    monkeypatch.setattr(fb, "run_full_backup", _ungated_backup)
    r = check_infrastructure()
    assert _check(r, "backup_gated_to_main")["ok"] is False and r["ok"] is False


def test_infra_check_catches_silent_except_regression(monkeypatch):
    import quoteforge.automation.code_auditor as ca
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr(ca, "run_full_audit", lambda send=False: {
        "regressions": [{"module": "x.py", "kind": "silent_except"}]})
    r = check_infrastructure()
    assert _check(r, "no_silent_except_regression")["ok"] is False and r["ok"] is False


def test_infra_check_catches_worktree_leak(monkeypatch):
    import quoteforge.automation.code_auditor as ca
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr(ca, "list_modules",
                        lambda: ["automation/x.py", ".claude/worktrees/y/q.py"])
    r = check_infrastructure()
    assert _check(r, "scans_exclude_worktrees")["ok"] is False and r["ok"] is False


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


def test_apparel_image_key_resolve_equals_display():
    # REGRESSION (#56): every apparel garment's image resolve-key (garment_id from
    # apparel_sku_for on sizes[0]) must equal the editor's display-key (APPGID
    # name->garment_id), else that garment silently shows no real product photo.
    import re
    from quoteforge.etsy.apparel_catalog import (
        APPAREL_CATALOG, apparel_sku_for, parse_apparel_format)
    display = {g.garment_id for g in APPAREL_CATALOG}
    resolve = {g.garment_id for g in APPAREL_CATALOG
               if g.sizes and g.colors
               and any(apparel_sku_for(g.garment_id, g.sizes[0], c) for c in g.colors)}
    assert resolve == display                       # no orphan on either side
    assert all(parse_apparel_format(f"{g.name} - {g.colors[0]}")[0] == g.garment_id
               for g in APPAREL_CATALOG)             # names unique, round-trip
    assert all(re.sub(r"_(value|premium)$", "", g.garment_id) in display
               for g in APPAREL_CATALOG)             # tier _bgid strips to a real base


def test_infra_check_catches_apparel_key_drift(monkeypatch):
    # GROUNDING: prove invariant #56 goes ok=False when a garment_id the editor
    # would request is not produced by the resolver. Decoy: make apparel_sku_for
    # return "" for one garment's colours so it drops out of the resolve-set.
    # infra_check imports apparel_sku_for fresh from the catalog module each call,
    # so patch the SOURCE symbol.
    from quoteforge.etsy import apparel_catalog as ac
    from quoteforge.automation.infra_check import check_infrastructure
    victim = ac.APPAREL_CATALOG[0].garment_id
    real_sku = ac.apparel_sku_for
    monkeypatch.setattr(
        "quoteforge.etsy.apparel_catalog.apparel_sku_for",
        lambda gid, size, color: "" if gid == victim else real_sku(gid, size, color))
    r = check_infrastructure()
    assert _check(r, "apparel_image_key_linkage")["ok"] is False
    assert r["ok"] is False


def test_framed_catalog_sellable_or_explicitly_held():
    # REGRESSION (#57): every prepared framed catalog size must be sold OR listed in
    # _FRAMED_UNSOLD_OK. 16x20 has a real framed UID but no 16x20 poster base, so it
    # is intentionally held (owner decision). The check must be green in this state.
    from quoteforge.automation.infra_check import check_infrastructure, _FRAMED_UNSOLD_OK
    from quoteforge.etsy.variations import build_variations, _ns
    from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
    sold = {_ns(v.size) for v in build_variations() if v.material == "framed"}
    cat = {_ns(p.size) for p in GELATO_CATALOG if p.category == "framed"}
    assert "16x20" in _FRAMED_UNSOLD_OK and "16x20" in cat and "16x20" not in sold
    r = check_infrastructure()
    assert _check(r, "framed_catalog_fully_sellable")["ok"] is True


def test_infra_check_catches_unheld_unsold_framed(monkeypatch):
    # GROUNDING: prove invariant #57 goes ok=False when a prepared framed size is
    # neither sold nor held. Decoy: empty the intentional-hold set so 16x20 (unsold,
    # real UID) becomes an unguarded invisible product.
    import quoteforge.automation.infra_check as ic
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr(ic, "_FRAMED_UNSOLD_OK", set())
    r = check_infrastructure()
    got = _check(r, "framed_catalog_fully_sellable")
    assert got["ok"] is False and "16x20" in got["detail"]
    assert r["ok"] is False


def test_branded_non_sellable_stays_quarantined():
    # REGRESSION (#58): every branded item declared non-sellable (phonecase) must
    # resolve NO routing SKU and report not-sellable, so we never take an order for
    # an item we can't fulfil. The check must be green in the shipped state.
    from quoteforge.automation.infra_check import check_infrastructure
    from quoteforge.etsy.branded_catalog import (
        NON_SELLABLE_BRANDED, branded_sku_for, branded_sellable)
    assert "phonecase" in NON_SELLABLE_BRANDED
    for p in NON_SELLABLE_BRANDED:
        assert branded_sellable(p) is False
        assert branded_sku_for(p, "M", "Black") is None
    r = check_infrastructure()
    assert _check(r, "branded_non_sellable_quarantined")["ok"] is True


def test_infra_check_catches_unquarantined_branded(monkeypatch):
    # GROUNDING: prove invariant #58 goes ok=False when a declared non-sellable item
    # leaks a routing SKU. Decoy: make branded_sku_for resolve a real SKU for a
    # quarantined item (as a refactor that stopped honouring the quarantine would).
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr(
        "quoteforge.etsy.branded_catalog.branded_sku_for",
        lambda pid, size, color: "GEL-PHONE-LEAK")
    r = check_infrastructure()
    got = _check(r, "branded_non_sellable_quarantined")
    assert got["ok"] is False and "phonecase" in got["detail"]
    assert r["ok"] is False


def test_infra_check_auditor_agents_assigned():
    # REGRESSION (#59): the code-outcome-auditor + storefront-fulfillability-auditor
    # agents that GROW infra-check must stay assigned. On a machine with .claude/agents
    # the check must be green (both files present with a declared name); on a host
    # without the dir it is skip-friendly (still green). Either way ok is True.
    from pathlib import Path
    import quoteforge
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    got = _check(r, "infra_check_auditor_agents_assigned")
    assert got["ok"] is True
    agents_dir = Path(quoteforge.__file__).resolve().parent.parent / ".claude" / "agents"
    if agents_dir.is_dir():   # dev/ops host: assert the real files really are present
        for name in ("code-outcome-auditor", "storefront-fulfillability-auditor"):
            assert (agents_dir / f"{name}.md").is_file()


def test_infra_check_catches_unassigned_auditor_agent(tmp_path, monkeypatch):
    # GROUNDING: prove invariant #59 goes ok=False when a required auditor agent is
    # NOT assigned. Point quoteforge.__file__ at a fake tree whose .claude/agents is
    # missing the code-outcome-auditor, so the check must detect the gap.
    import quoteforge
    from quoteforge.automation.infra_check import check_infrastructure
    pkg = tmp_path / "quoteforge"
    (pkg).mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    # only ONE of the two required agents is assigned -> the other must be flagged
    (agents / "storefront-fulfillability-auditor.md").write_text(
        "---\nname: storefront-fulfillability-auditor\n---\n", encoding="utf-8")
    monkeypatch.setattr(quoteforge, "__file__", str(pkg / "__init__.py"))
    r = check_infrastructure()
    got = _check(r, "infra_check_auditor_agents_assigned")
    assert got["ok"] is False and "code-outcome-auditor" in got["detail"]
    assert r["ok"] is False
