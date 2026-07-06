"""Integration Manager — unified credential lifecycle (doctor + scope diff + setup).

Pins the enterprise-onboarding guarantees:
  - a granted-vs-required Etsy scope diff exists and flags a MISSING scope
  - the scope Etsy grants is CAPTURED at token exchange and PRESERVED across refresh
  - doctor(probe=False) is hermetic (no network) and well-formed
  - the setup checklist reflects real credential presence, not health-skips
  - the whole thing is wired into COMMANDS + scheduler + a daily infra-check invariant
All local; no network.
"""
import json

import pytest

from quoteforge.automation import integration_manager as im
from quoteforge.automation import etsy_auth


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    f = tmp_path / "etsy_tokens.json"
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(f))
    return f


# ── scope diff (the new capability) ───────────────────────────────────────────

def test_scope_status_flags_missing_scope(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(cfg, "ETSY_API_KEY", "app-key")
    monkeypatch.setattr(cfg, "ETSY_OAUTH_SCOPES", "transactions_r listings_r listings_w email_r")
    monkeypatch.setattr(im, "_import", im._import)  # keep real
    monkeypatch.setattr(etsy_auth, "current_access_token", lambda: "tok")
    monkeypatch.setattr(etsy_auth, "current_granted_scopes", lambda: "transactions_r listings_r")
    s = im.scope_status()
    assert s["ok"] is False
    assert set(s["missing"]) == {"listings_w", "email_r"}


def test_scope_status_all_granted(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(cfg, "ETSY_API_KEY", "app-key")
    monkeypatch.setattr(cfg, "ETSY_OAUTH_SCOPES", "listings_r listings_w")
    monkeypatch.setattr(etsy_auth, "current_access_token", lambda: "tok")
    monkeypatch.setattr(etsy_auth, "current_granted_scopes", lambda: "listings_w listings_r email_r")
    s = im.scope_status()
    assert s["ok"] is True and s["missing"] == []


def test_scope_status_skips_in_test_mode(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "TEST_MODE", True)
    s = im.scope_status()
    assert s["ok"] is True and "skipped" in s["detail"]
    assert isinstance(s["required"], list)


# ── scope capture at exchange + preservation on refresh ───────────────────────

def test_scope_captured_at_exchange(token_file, monkeypatch):
    # exchange_code must persist the scope Etsy granted, readable via current_granted_scopes.
    from quoteforge.automation import etsy_oauth
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "ETSY_API_KEY", "app-key")
    monkeypatch.setattr(cfg, "ETSY_OAUTH_REDIRECT_URI", "https://x/cb")
    # seed a pending PKCE state so exchange proceeds
    sf = etsy_oauth._state_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"code_verifier": "v", "state": "s"}), encoding="utf-8")
    fake = {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600,
            "scope": "transactions_r listings_r listings_w email_r"}
    out = etsy_oauth.exchange_code("code123", "s", poster=lambda url, data: fake)
    assert out["ok"] is True
    assert etsy_auth.current_granted_scopes() == "transactions_r listings_r listings_w email_r"


def test_scope_preserved_on_refresh_without_scope(token_file):
    # A refresh response that omits scope must NOT erase the previously-granted scope.
    etsy_auth._save("AT", "RT", 3600, scope="listings_r listings_w")
    etsy_auth._save("AT2", "RT2", 3600, scope=None)     # refresh without scope echo
    assert etsy_auth.current_granted_scopes() == "listings_r listings_w"


# ── doctor: hermetic + well-formed ────────────────────────────────────────────

def test_doctor_probe_false_makes_no_network_call(monkeypatch):
    # With probe=False the doctor must NOT call the live Gelato/Etsy auth probes.
    import quoteforge.automation.gelato_api as ga
    def _boom():
        raise AssertionError("verify_gelato_auth must not be called with probe=False")
    monkeypatch.setattr(ga, "verify_gelato_auth", _boom)
    d = im.doctor(probe=False)
    assert d["verdict"] in ("GO", "FIX-FIRST")
    assert set(("gelato_auth", "etsy_auth", "etsy_scopes", "gelato_store")) <= set(d["components"])


def test_doctor_shape():
    d = im.doctor(probe=False)
    assert isinstance(d["blockers"], list)
    assert "etsy_scopes" in d["components"]
    # format_report never raises and mentions the verdict
    assert d["verdict"] in im.format_report(d)


# ── setup checklist reflects real presence, not health-skips ──────────────────

def test_setup_checklist_marks_unconnected_etsy_not_done(token_file, monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "ETSY_API_KEY", "app-key")     # app registered...
    monkeypatch.setattr(etsy_auth, "current_access_token", lambda: "")   # ...but not connected
    steps = {s["step"]: s["done"] for s in im.setup_checklist()}
    assert steps["Connect Etsy (OAuth)"] is False


# ── wiring: command + scheduler + invariant ───────────────────────────────────

def test_integration_command_and_schedule_wired():
    from quoteforge.admin import COMMANDS
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    assert "integration" in COMMANDS
    assert any(j.admin_args.split()[0] == "integration" for j in SCHEDULED_JOBS)


def test_infra_invariant_integration_manager_wired():
    from quoteforge.automation.infra_check import check_infrastructure
    hit = [c for c in check_infrastructure()["checks"]
           if c["name"] == "integration_manager_wired"]
    assert hit and hit[0]["ok"] is True
