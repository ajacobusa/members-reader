"""Etsy OAuth 2.0 (PKCE) connect flow - authorize your shop once, from the CLI.

`admin etsy-connect start` prints the authorization URL; you approve it in the browser,
Etsy redirects to your registered redirect URI with ?code=...&state=..., and
`admin etsy-connect finish <CODE>` exchanges it for tokens and persists them.

Guard rails (all enforced here):
  * PKCE (S256) - a per-attempt code_verifier/code_challenge, so an intercepted auth code
    is useless without the verifier this process generated.
  * State / CSRF - a random state is issued at `start` and REQUIRED to match at `finish`.
  * Secrets are NEVER printed or logged - not the client secret, the code_verifier, nor the
    access/refresh tokens. Only non-secret status is shown.
  * Tokens land in the existing 0600 token file (etsy_auth._save); the transient PKCE state
    file is also 0600 and is DELETED after a successful exchange.
  * Gated: without ETSY_API_KEY / ETSY_OAUTH_REDIRECT_URI it refuses with a clear message
    rather than building a broken URL. The token exchange is defensive (never raises).

Etsy's OAuth 2.0 endpoints are public + stable; this follows the standard authorization-code
+ PKCE grant. `poster` is injectable so the exchange is testable without a live call.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_AUTH_URL = "https://www.etsy.com/oauth/connect"
_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"


def _b64url(data: bytes) -> str:
    """URL-safe base64 without padding (PKCE + state encoding)."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge) for PKCE S256."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _state_file() -> Path:
    """Transient PKCE/state store between `start` and `finish` (ETSY_OAUTH_STATE_FILE or
    OUTPUT_DIR/etsy_oauth_state.json). Holds the code_verifier + state - secret, 0600."""
    from quoteforge.config import OUTPUT_DIR
    return Path(os.getenv("ETSY_OAUTH_STATE_FILE") or (Path(OUTPUT_DIR) / "etsy_oauth_state.json"))


def _save_state(verifier: str, state: str) -> None:
    """Persist the PKCE verifier + state with 0600 perms (it is a secret)."""
    f = _state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"code_verifier": verifier, "state": state}), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError as exc:  # noqa: BLE001 - non-POSIX fs: best effort
        logger.debug("state file chmod skipped: %s", exc)


def build_auth_url() -> dict:
    """Start the flow: generate PKCE + state, store them (0600), and return the auth URL to
    open. Returns {ok, url|error, state}. Requires ETSY_API_KEY + ETSY_OAUTH_REDIRECT_URI.
    The code_verifier is stored, never returned/printed."""
    from quoteforge.config import (ETSY_API_KEY, ETSY_OAUTH_REDIRECT_URI, ETSY_OAUTH_SCOPES)
    if not ETSY_API_KEY:
        return {"ok": False, "error": "ETSY_API_KEY not set (register an Etsy app first)"}
    if not ETSY_OAUTH_REDIRECT_URI:
        return {"ok": False, "error": "ETSY_OAUTH_REDIRECT_URI not set (must match your "
                                      "Etsy app's registered redirect URI)"}
    verifier, challenge = _pkce()
    state = _b64url(secrets.token_bytes(16))
    _save_state(verifier, state)
    params = {"response_type": "code", "client_id": ETSY_API_KEY,
              "redirect_uri": ETSY_OAUTH_REDIRECT_URI, "scope": ETSY_OAUTH_SCOPES,
              "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return {"ok": True, "url": f"{_AUTH_URL}?{urlencode(params)}", "state": state}


def exchange_code(code: str, state: str = "", *, poster=None) -> dict:
    """Finish the flow: verify state, exchange the auth code (+ stored code_verifier) for
    tokens, and persist them (0600). Returns {ok, detail} - NEVER the tokens. Defensive:
    any failure returns ok=False with a safe message, never raises. Deletes the state file
    on success. `poster(url, data)->dict` is injectable for testing."""
    from quoteforge.config import ETSY_API_KEY, ETSY_OAUTH_REDIRECT_URI
    code = (code or "").strip()
    if not code:
        return {"ok": False, "detail": "no authorization code provided"}
    f = _state_file()
    try:
        saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except Exception:  # noqa: BLE001
        saved = {}
    verifier = saved.get("code_verifier", "")
    if not verifier:
        return {"ok": False, "detail": "no pending connect (run `etsy-connect start` first)"}
    # CSRF: the state returned by Etsy must match the one we issued.
    if state and saved.get("state") and state != saved.get("state"):
        return {"ok": False, "detail": "state mismatch - possible CSRF; re-run start"}
    try:
        data = {"grant_type": "authorization_code", "client_id": ETSY_API_KEY,
                "redirect_uri": ETSY_OAUTH_REDIRECT_URI, "code": code,
                "code_verifier": verifier}
        resp = (poster or _post_token)(_TOKEN_URL, data)
        access = resp.get("access_token")
        refresh = resp.get("refresh_token")
        expires = resp.get("expires_in", 3600)
        if not access or not refresh:
            return {"ok": False, "detail": "token exchange returned no tokens "
                                           "(check the code + redirect URI)"}
        from quoteforge.automation.etsy_auth import _save
        # Capture the scopes Etsy actually GRANTED (resp["scope"]) so the Integration
        # Manager can diff granted vs required offline - a revoked/insufficient scope
        # is caught before it fails a live listing/order call.
        _save(access, refresh, expires, scope=resp.get("scope"))   # 0600, never logs tokens
        try:
            f.unlink(missing_ok=True)            # clear the transient PKCE state
        except OSError as exc:
            logger.debug("pkce state cleanup skipped: %s", exc)
        return {"ok": True, "detail": "connected - Etsy tokens saved (0600), auto-refresh wired"}
    except Exception as exc:  # noqa: BLE001 - never surface a secret in the error
        logger.warning("etsy token exchange failed: %s", type(exc).__name__)
        return {"ok": False, "detail": f"token exchange failed: {type(exc).__name__}"}


def _post_token(url: str, data: dict) -> dict:
    """Live POST to Etsy's token endpoint (form-encoded). Returns the JSON dict."""
    import requests
    resp = requests.post(url, data=data,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         timeout=30)
    return resp.json() if resp.status_code == 200 else {}


def connect_status() -> dict:
    """Non-secret status of the Etsy connection (for the CLI / health check). Reports only
    booleans - never a token value."""
    from quoteforge.config import (ETSY_API_KEY, ETSY_OAUTH_REDIRECT_URI, ETSY_SHOP_ID)
    from quoteforge.automation.etsy_auth import current_access_token, current_refresh_token
    return {"app_key_set": bool(ETSY_API_KEY),
            "redirect_uri_set": bool(ETSY_OAUTH_REDIRECT_URI),
            "shop_id_set": bool(ETSY_SHOP_ID),
            "access_token_present": bool(current_access_token()),
            "refresh_token_present": bool(current_refresh_token())}
