"""Etsy OAuth2 token auto-refresh.

Etsy v3 access tokens expire ~1 hour after issuance. Without refresh, the static
ETSY_OAUTH_TOKEN dies an hour after go-live and order intake silently stalls. This
module exchanges the refresh token for a fresh access token (Etsy rotates the refresh
token on each use), persists BOTH to a token file, and retries the failed call.

  current_access_token() - the freshest token (persisted, else the env seed).
  refresh_access_token()  - exchange + persist; None on failure / no creds / TEST_MODE.
  with_refresh(call, ...) - run call(); on a 401, refresh once and retry.

TEST_MODE / no creds is a hard no-op (the Etsy API client already returns mocks).

Persistence note: tokens are stored in OUTPUT_DIR/etsy_tokens.json (override with
ETSY_TOKEN_FILE). On a single host this survives restarts; on split web+cron services
(e.g. Render's per-service disks) point ETSY_TOKEN_FILE at shared storage.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"


def _token_file() -> Path:
    """Path to the persisted token file (ETSY_TOKEN_FILE, else OUTPUT_DIR/etsy_tokens.json)."""
    import os
    from quoteforge.config import OUTPUT_DIR
    return Path(os.getenv("ETSY_TOKEN_FILE") or (Path(OUTPUT_DIR) / "etsy_tokens.json"))


def _load() -> dict:
    """The persisted token dict ({} if the file is absent/corrupt). Transparently
    decrypts an at-rest-encrypted file (secret_store); a legacy plaintext file still
    reads and is re-encrypted on the next save."""
    from quoteforge.automation.secret_store import load_json
    return load_json(_token_file())


def _save(access: str, refresh: str, expires_in, scope: str | None = None) -> None:
    """Persist the access + (rotated) refresh token and an expiry (60s safety margin),
    ENCRYPTED at rest when QF_SECRET_KEY is set (else 0600 plaintext). ``scope`` (the
    space-separated scopes Etsy granted this token) is persisted when provided; when None
    the previously-persisted scope is preserved (a refresh that omits it must not erase
    it) - so the Integration Manager can diff granted vs required scopes offline."""
    from quoteforge.automation.secret_store import save_json
    prev_scope = _load().get("scope", "")
    save_json(_token_file(), {
        "access_token": access, "refresh_token": refresh,
        "expires_at": time.time() + int(expires_in or 3600) - 60,  # 60s safety margin
        "scope": (scope if scope is not None else prev_scope) or "",
    })


def current_access_token() -> str:
    """The freshest Etsy access token: the persisted one, else the env seed."""
    from quoteforge.config import ETSY_OAUTH_TOKEN
    return _load().get("access_token") or ETSY_OAUTH_TOKEN


def current_refresh_token() -> str:
    """The current Etsy refresh token: the persisted (rotated) one, else the env seed."""
    from quoteforge.config import ETSY_REFRESH_TOKEN
    return _load().get("refresh_token") or ETSY_REFRESH_TOKEN


def current_granted_scopes() -> str:
    """The space-separated scopes Etsy granted the persisted token ('' if unknown -
    e.g. an env-seed token or a pre-scope-capture connection). Non-secret."""
    return _load().get("scope", "") or ""


def refresh_access_token() -> "str | None":
    """Exchange the refresh token for a new access token; persist + return it. Returns
    None on failure / no creds / TEST_MODE (the caller then surfaces the auth failure)."""
    import requests
    from quoteforge.config import TEST_MODE, ETSY_API_KEY
    rt = current_refresh_token()
    if TEST_MODE or not (ETSY_API_KEY and rt):
        return None
    try:
        resp = requests.post(_OAUTH_TOKEN_URL, data={
            "grant_type": "refresh_token", "client_id": ETSY_API_KEY,
            "refresh_token": rt}, timeout=30)
        resp.raise_for_status()
        d = resp.json()
        access = d.get("access_token")
        if access:
            # Preserve/refresh the granted scope (Etsy echoes it on refresh too).
            _save(access, d.get("refresh_token") or rt, d.get("expires_in"),
                  scope=d.get("scope"))
            logger.info("Etsy access token refreshed")
            return access
    except Exception as exc:  # noqa: BLE001
        logger.error("Etsy token refresh failed: %s", exc)
    return None


def is_unauthorized(exc: BaseException) -> bool:
    """True when an exception is an HTTP 401 (expired/invalid token)."""
    return getattr(getattr(exc, "response", None), "status_code", 0) == 401


def with_refresh(call):
    """Run ``call()`` (a zero-arg callable that uses the CURRENT token via _headers).
    On a 401, refresh the token once and retry; otherwise re-raise."""
    try:
        return call()
    except Exception as exc:  # noqa: BLE001
        if is_unauthorized(exc) and refresh_access_token():
            return call()                      # retry once with the fresh token
        raise


def token_expiry_status(warn_within_hours: int = 24) -> dict:
    """PROACTIVE, no-network health probe (#182-P1): is the Etsy access token healthy,
    or about to expire with NO way to refresh? A token that expires with no refresh
    token silently stalls order intake (see module docstring), so we want to catch it
    BEFORE the first 401, not after. Returns {ok, detail}. TEST_MODE / no creds is a
    skipped OK (a fresh install must not false-alarm). Auto-refreshable near-expiry is
    OK (with_refresh handles it); only near-expiry WITHOUT a refresh token is a WARN."""
    from quoteforge.config import TEST_MODE, ETSY_API_KEY
    if TEST_MODE or not ETSY_API_KEY:
        return {"ok": True, "detail": "skipped (TEST_MODE / creds not set)"}
    data = _load()
    exp = data.get("expires_at")
    if not exp:                                        # env seed in use, expiry unknown
        return {"ok": True, "detail": "no persisted token yet (env seed)"}
    remaining = float(exp) - time.time()
    if remaining > warn_within_hours * 3600:
        return {"ok": True, "detail": f"access token valid ~{int(remaining / 3600)}h"}
    if current_refresh_token():                        # near/at expiry but recoverable
        return {"ok": True, "detail": "near expiry but a refresh token is available"}
    return {"ok": False,
            "detail": "access token expiring and NO refresh token — order intake "
                      "will stall; re-run the Etsy OAuth flow"}


def verify_etsy_auth() -> dict:
    """Cheap authenticated probe for healthcheck: True iff a 1-row receipts call
    succeeds (refreshing if needed). {ok, detail}. TEST_MODE/no creds -> ok (skipped)."""
    from quoteforge.config import TEST_MODE
    from quoteforge.automation.etsy_api import _credentials_ready
    if TEST_MODE or not _credentials_ready():
        return {"ok": True, "detail": "skipped (TEST_MODE / creds not set)"}
    try:
        from quoteforge.automation.etsy_api import get_shop_receipts
        get_shop_receipts(limit=1)             # wrapped in with_refresh internally
        return {"ok": True, "detail": "authenticated"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"Etsy auth failed: {exc}"}
