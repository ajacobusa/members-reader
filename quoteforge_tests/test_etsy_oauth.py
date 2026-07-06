"""Etsy OAuth 2.0 (PKCE) connect flow - guard-railed. PKCE + state/CSRF, tokens stored
0600 and NEVER printed/returned, gated without app key/redirect, defensive exchange.
"""
import json

import pytest

from quoteforge.automation import etsy_oauth as oa


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("ETSY_OAUTH_STATE_FILE", str(tmp_path / "st.json"))
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(tmp_path / "tok.json"))
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    return tmp_path


def _live(monkeypatch):
    monkeypatch.setattr("quoteforge.config.ETSY_API_KEY", "appkey")
    monkeypatch.setattr("quoteforge.config.ETSY_OAUTH_REDIRECT_URI", "https://x/cb")


def test_start_gated_without_key_or_redirect(iso, monkeypatch):
    monkeypatch.setattr("quoteforge.config.ETSY_API_KEY", "")
    assert oa.build_auth_url()["ok"] is False
    monkeypatch.setattr("quoteforge.config.ETSY_API_KEY", "appkey")
    monkeypatch.setattr("quoteforge.config.ETSY_OAUTH_REDIRECT_URI", "")
    assert oa.build_auth_url()["ok"] is False


def test_auth_url_has_pkce_and_state_and_no_verifier_leak(iso, monkeypatch):
    _live(monkeypatch)
    r = oa.build_auth_url()
    assert r["ok"] and "code_challenge=" in r["url"]
    assert "code_challenge_method=S256" in r["url"] and "state=" in r["url"]
    assert "code_verifier" not in r["url"]                 # the secret never goes on the URL


def test_exchange_rejects_state_mismatch(iso, monkeypatch):
    _live(monkeypatch)
    oa.build_auth_url()
    r = oa.exchange_code("CODE", state="WRONG",
                         poster=lambda u, d: {"access_token": "A", "refresh_token": "B"})
    assert r["ok"] is False and "csrf" in r["detail"].lower()


def test_exchange_saves_tokens_0600_without_leaking(iso, monkeypatch):
    _live(monkeypatch)
    started = oa.build_auth_url()
    res = oa.exchange_code("CODE", state=started["state"],
                           poster=lambda u, d: {"access_token": "AT", "refresh_token": "RT",
                                                "expires_in": 3600})
    assert res["ok"] is True
    # the RESULT never contains the token values
    assert "AT" not in json.dumps(res) and "RT" not in json.dumps(res)
    tok = json.loads((iso / "tok.json").read_text())
    assert tok["access_token"] == "AT" and tok["refresh_token"] == "RT"
    assert not (iso / "st.json").exists()                  # transient PKCE state cleared


def test_exchange_without_pending_state_is_error(iso, monkeypatch):
    _live(monkeypatch)
    r = oa.exchange_code("CODE", poster=lambda u, d: {"access_token": "A"})
    assert r["ok"] is False and "start" in r["detail"].lower()


def test_exchange_no_tokens_returned_is_error(iso, monkeypatch):
    _live(monkeypatch)
    oa.build_auth_url()
    r = oa.exchange_code("CODE", poster=lambda u, d: {})    # provider returned nothing
    assert r["ok"] is False


def test_connect_status_is_booleans_only(iso, monkeypatch):
    _live(monkeypatch)
    st = oa.connect_status()
    assert set(st) == {"app_key_set", "redirect_uri_set", "shop_id_set",
                       "access_token_present", "refresh_token_present"}
    assert all(isinstance(v, bool) for v in st.values())


def test_cli_etsy_connect(iso, capsys):
    from quoteforge import admin
    assert admin.main(["etsy-connect", "status"]) == 1     # not connected yet
    assert "Etsy connect" in capsys.readouterr().out
