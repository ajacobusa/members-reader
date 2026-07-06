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


# ── #5: credential encryption at rest ─────────────────────────────────────────

def test_encryption_roundtrip_and_ciphertext_on_disk(tmp_path, monkeypatch):
    # With a key set, the token store writes CIPHERTEXT (secret not on disk) + round-trips.
    from quoteforge.automation import secret_store as ss
    key = ss.generate_key()
    monkeypatch.setenv("QF_SECRET_KEY", key)
    p = tmp_path / "tok.json"
    payload = {"access_token": "TOP_SECRET_TOKEN", "scope": "listings_r"}
    ss.save_json(p, payload)
    raw = p.read_bytes()
    assert raw.startswith(b"QF_ENC1:")
    assert b"TOP_SECRET_TOKEN" not in raw            # plaintext secret never hits disk
    assert ss.load_json(p) == payload                # round-trips
    st = ss.encryption_status()
    assert st["encrypted"] is True and st["ok"] is True


def test_plaintext_fallback_without_key(tmp_path, monkeypatch):
    from quoteforge.automation import secret_store as ss
    monkeypatch.delenv("QF_SECRET_KEY", raising=False)
    p = tmp_path / "tok.json"
    ss.save_json(p, {"access_token": "AT"})
    assert ss.load_json(p) == {"access_token": "AT"}   # 0600 plaintext still round-trips
    st = ss.encryption_status()
    assert st["encrypted"] is False and st["ok"] is True   # available-but-inactive is OK


def test_legacy_plaintext_migrates_to_encrypted_on_next_save(tmp_path, monkeypatch):
    import json as _json
    from quoteforge.automation import secret_store as ss
    p = tmp_path / "tok.json"
    p.write_bytes(_json.dumps({"access_token": "LEGACY"}).encode())   # legacy plaintext
    monkeypatch.setenv("QF_SECRET_KEY", ss.generate_key())
    assert ss.load_json(p) == {"access_token": "LEGACY"}   # reads legacy transparently
    ss.save_json(p, {"access_token": "LEGACY2"})           # re-save -> now encrypted
    assert p.read_bytes().startswith(b"QF_ENC1:")


def test_etsy_auth_uses_encrypted_store(tmp_path, monkeypatch):
    # The Etsy token persistence path is encrypted end-to-end when a key is set.
    from quoteforge.automation import etsy_auth, secret_store as ss
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(tmp_path / "etsy_tokens.json"))
    monkeypatch.setenv("QF_SECRET_KEY", ss.generate_key())
    etsy_auth._save("ACCESS_X", "REFRESH_Y", 3600, scope="listings_r listings_w")
    raw = (tmp_path / "etsy_tokens.json").read_bytes()
    assert raw.startswith(b"QF_ENC1:") and b"REFRESH_Y" not in raw
    assert etsy_auth.current_access_token() == "ACCESS_X"
    assert etsy_auth.current_granted_scopes() == "listings_r listings_w"


def test_infra_invariant_encryption_at_rest():
    from quoteforge.automation.infra_check import check_infrastructure
    hit = [c for c in check_infrastructure()["checks"]
           if c["name"] == "credential_encryption_at_rest"]
    assert hit and hit[0]["ok"] is True


# ── auditor follow-ups: pure scope diff, unknown-scope WARN, encrypted PKCE state ─

def test_scope_diff_pure_detects_missing():
    # REGRESSION: the pure diff (the testable core the invariant guards) must flag
    # exactly the required scopes absent from granted.
    d = im._scope_diff("listings_r transactions_r", "listings_r listings_w email_r")
    assert d["missing"] == ["email_r", "listings_w"]
    assert im._scope_diff("a b", "a b")["missing"] == []


def test_scope_status_warns_on_unknown_but_connected(monkeypatch):
    # A live, connected token whose granted scopes are UNKNOWN must WARN (nudge to
    # reconnect), not silently PASS.
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(cfg, "ETSY_API_KEY", "app-key")
    monkeypatch.setattr(etsy_auth, "current_access_token", lambda: "tok")
    monkeypatch.setattr(etsy_auth, "current_granted_scopes", lambda: "")   # unknown
    s = im.scope_status()
    assert s["ok"] is True and s["warn"] is True
    d = im.doctor(probe=False)
    # the warn surfaces in the doctor roll-up
    assert any("etsy_scopes" in w for w in d["warns"])


def test_pkce_state_encrypted_at_rest(tmp_path, monkeypatch):
    # REGRESSION: the transient PKCE state file is covered by the same at-rest
    # encryption as the token file (every persisted credential-adjacent file).
    from quoteforge.automation import etsy_oauth, secret_store as ss
    monkeypatch.setenv("ETSY_OAUTH_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("QF_SECRET_KEY", ss.generate_key())
    etsy_oauth._save_state("VERIFIER_SECRET", "state123")
    raw = (tmp_path / "state.json").read_bytes()
    assert raw.startswith(b"QF_ENC1:") and b"VERIFIER_SECRET" not in raw
    # and exchange_code can still read it back (transparently decrypts)
    assert ss.load_json(tmp_path / "state.json")["code_verifier"] == "VERIFIER_SECRET"
