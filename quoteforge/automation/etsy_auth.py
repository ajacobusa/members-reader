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
    """The persisted token dict ({} if the file is absent or corrupt)."""
    f = _token_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - a corrupt token file falls back to the env seed
            return {}
    return {}


def _save(access: str, refresh: str, expires_in) -> None:
    """Persist the access + (rotated) refresh token and an expiry (60s safety margin)."""
    f = _token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({
        "access_token": access, "refresh_token": refresh,
        "expires_at": time.time() + int(expires_in or 3600) - 60,  # 60s safety margin
    }), encoding="utf-8")
    # Restrict the refresh-token file to the owner (#182). Best-effort: no-op on
    # filesystems without POSIX perms (Windows), never breaks the refresh.
    try:
        import os as _os
        _os.chmod(f, 0o600)
    except OSError as exc:  # noqa: BLE001
        logger.debug("token file chmod skipped: %s", exc)


def current_access_token() -> str:
    """The freshest Etsy access token: the persisted one, else the env seed."""
    from quoteforge.config import ETSY_OAUTH_TOKEN
    return _load().get("access_token") or ETSY_OAUTH_TOKEN


def current_refresh_token() -> str:
    """The current Etsy refresh token: the persisted (rotated) one, else the env seed."""
    from quoteforge.config import ETSY_REFRESH_TOKEN
    return _load().get("refresh_token") or ETSY_REFRESH_TOKEN


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
            _save(access, d.get("refresh_token") or rt, d.get("expires_in"))
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
