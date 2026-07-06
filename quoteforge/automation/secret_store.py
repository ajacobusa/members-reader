"""At-rest encryption for persisted credential files (Integration Manager, #5).

The one persisted secret we hold is the Etsy OAuth token file. File permissions (0600)
protect it from other local users, but not from a stolen disk/backup. This adds
authenticated encryption at rest (Fernet / AES-128-CBC + HMAC) with the key sourced
from the environment (``QF_SECRET_KEY``) - never stored next to the ciphertext, which
would be theater.

Design (honest about the threat model):
  * The key lives in ``QF_SECRET_KEY`` (the platform's encrypted env store), NOT on disk.
  * When a valid key + ``cryptography`` are present, the file is written encrypted with a
    ``QF_ENC1:`` sentinel; otherwise it falls back to plaintext + 0600 (prior behavior),
    so a stripped install or a not-yet-configured deploy still works.
  * A legacy plaintext file is read transparently and RE-ENCRYPTED on the next save
    (auto-migration) once a key is set.
  * Never logs a token or the key.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_SENTINEL = b"QF_ENC1:"        # marks an encrypted payload (vs legacy plaintext JSON)


def _enc_key() -> str:
    """The at-rest encryption key from the environment ('' if unset). Non-secret to
    read the PRESENCE of; the value itself is never logged."""
    return (os.getenv("QF_SECRET_KEY") or "").strip()


def _fernet():
    """A Fernet cipher for the configured key, or None when unavailable (no key, invalid
    key, or cryptography not installed). Never raises."""
    key = _enc_key()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - bad key / lib missing -> plaintext fallback
        logger.warning("at-rest encryption unavailable (using 0600 plaintext): %s", exc)
        return None


def generate_key() -> str:
    """A fresh Fernet key to put in QF_SECRET_KEY (one-time, owner-run). Raises if
    cryptography is unavailable - callers surface a clear message."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("utf-8")


def _chmod_600(path: Path) -> None:
    """Best-effort owner-only perms (defense-in-depth alongside encryption)."""
    try:
        os.chmod(path, 0o600)
    except OSError as exc:  # noqa: BLE001 - no POSIX perms (Windows) -> encryption still applies
        logger.debug("secret file chmod skipped: %s", exc)


def save_json(path: Path, obj: dict) -> None:
    """Persist ``obj`` as JSON, ENCRYPTED at rest when a key is configured, else plaintext
    (0600 either way). Never raises the encryption path silently - a configured-but-broken
    key falls back to plaintext with a warning rather than losing the token."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj).encode("utf-8")
    f = _fernet()
    if f is not None:
        try:
            path.write_bytes(_SENTINEL + f.encrypt(raw))
            _chmod_600(path)
            return
        except Exception as exc:  # noqa: BLE001 - encrypt failure -> plaintext, never lose data
            logger.warning("encrypt-at-rest failed, writing 0600 plaintext: %s", exc)
    path.write_bytes(raw)
    _chmod_600(path)


def load_json(path: Path) -> dict:
    """Load JSON written by ``save_json``, decrypting transparently. A legacy plaintext
    file reads fine (and re-encrypts on the next save). Returns {} on missing/corrupt/
    undecryptable (never raises)."""
    if not path.exists():
        return {}
    try:
        data = path.read_bytes()
    except OSError as exc:
        logger.debug("secret file read failed: %s", exc)
        return {}
    if data.startswith(_SENTINEL):
        f = _fernet()
        if f is None:
            logger.error("credential file is encrypted but no valid QF_SECRET_KEY is set")
            return {}
        try:
            return json.loads(f.decrypt(data[len(_SENTINEL):]).decode("utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - wrong key / tampered -> empty, surfaced
            logger.error("credential decrypt failed (wrong QF_SECRET_KEY?): %s", exc)
            return {}
    try:
        return json.loads(data.decode("utf-8") or "{}") or {}
    except Exception as exc:  # noqa: BLE001 - corrupt plaintext -> empty
        logger.debug("plaintext credential parse failed: %s", exc)
        return {}


def encryption_status() -> dict:
    """Report at-rest encryption state for the Integration Manager. {ok, encrypted, detail}.
    ok is False only when a key IS set but unusable (misconfiguration to surface); an unset
    key is ok (available-but-inactive: 0600 plaintext, the owner can enable it any time)."""
    key = _enc_key()
    if not key:
        return {"ok": True, "encrypted": False,
                "detail": "at-rest encryption available but inactive - set QF_SECRET_KEY "
                "to encrypt the token file (currently 0600 plaintext)"}
    if _fernet() is None:
        return {"ok": False, "encrypted": False,
                "detail": "QF_SECRET_KEY set but invalid or cryptography missing"}
    return {"ok": True, "encrypted": True,
            "detail": "credential file encrypted at rest (Fernet), key from env"}
