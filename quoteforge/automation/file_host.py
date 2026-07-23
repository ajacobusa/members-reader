"""Publish a customer print file to a public URL the print partner can fetch.

Order of preference (first that works wins):
  1. A local public directory served at PUBLIC_FILE_BASE_URL (the webhook
     server's own /files route) - copies the file in and returns
     base_url/token-name. Preferred: one infra dependency, files stay under our
     control (deletable, no third-party quota), no public-forever links.
  2. Google Drive (service account) - returns a direct-download link. Fallback
     only: uc?export=download is not a contractual CDN (interstitial HTML,
     quota errors) and makes the file publicly readable indefinitely.
  3. Fallback: the local file:// URI (works in TEST_MODE / local dev only).

Published filenames are the file's CONTENT HASH (sha256), never the original
name: no customer email/order id leaks into the URL, the URL is not enumerable
(a capability URL - guessing it requires the file bytes), and re-publishing the
same file is idempotent (same name, no accumulation in the public dir).

The LOCAL copy in the customer folder is always kept regardless - publishing only
adds an off-machine, fetchable URL. Never raises; returns a result dict.
"""
from __future__ import annotations
import hashlib
import logging
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".pdf": "application/pdf", ".tif": "image/tiff", ".tiff": "image/tiff"}


def published_name(local_path) -> str:
    """Non-enumerable published filename: sha256(content) + the (whitelisted)
    extension. Deterministic, so re-publishing the same file yields the same
    URL; unguessable without the file bytes; carries no customer identifier."""
    p = Path(local_path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    ext = p.suffix.lower()
    if ext not in _MIME:
        ext = ".bin"
    return f"{h.hexdigest()[:40]}{ext}"


def active_backend() -> dict:
    """Which hosting backend would be used right now (without uploading anything).
    Returns {backend, public, detail}."""
    try:
        from quoteforge.config import PUBLIC_FILE_BASE_URL, PUBLIC_FILE_DIR
        if PUBLIC_FILE_BASE_URL and PUBLIC_FILE_DIR:
            return {"backend": "public_dir", "public": True,
                    "detail": f"public dir -> {PUBLIC_FILE_BASE_URL}"}
    except Exception as exc:  # noqa: BLE001 - probe only, fall through to next backend
        logger.debug("public-dir backend probe failed: %s", exc)
    try:
        from quoteforge.automation.google_drive_client import is_configured
        if is_configured():
            return {"backend": "google_drive", "public": True,
                    "detail": "Google Drive (direct-download links; fallback backend)"}
    except Exception as exc:  # noqa: BLE001 - probe only, fall through to local
        logger.debug("drive backend probe failed: %s", exc)
    return {"backend": "local", "public": False,
            "detail": "local file:// only (not fetchable by the print partner - set "
                      "PUBLIC_FILE_DIR + PUBLIC_FILE_BASE_URL (preferred) or Google "
                      "Drive before go-live)"}


def publish_print_file(local_path) -> dict:
    """Return {url, host, public, local}. `local` is always the kept local copy."""
    p = Path(local_path)
    out = {"url": "", "host": "none", "public": False, "local": str(p)}
    if not p.exists():
        return out
    mimetype = _MIME.get(p.suffix.lower(), "application/octet-stream")
    try:
        name = published_name(p)
    except Exception as exc:  # noqa: BLE001 - unreadable file = nothing to publish
        logger.warning("publish: could not hash %s (not published): %s", p, exc)
        return out

    # 1) Local public directory served at PUBLIC_FILE_BASE_URL (preferred)
    try:
        from quoteforge.config import PUBLIC_FILE_BASE_URL, PUBLIC_FILE_DIR
        if PUBLIC_FILE_BASE_URL and PUBLIC_FILE_DIR:
            dest_dir = Path(PUBLIC_FILE_DIR)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            if not dest.exists():          # content-hash name -> same bytes, skip copy
                shutil.copy2(p, dest)
            out.update({"url": f"{PUBLIC_FILE_BASE_URL}/{name}",
                        "host": "public_dir", "public": True})
            return out
    except Exception as exc:  # noqa: BLE001 - never raise; try the next backend
        logger.warning("public-dir publish failed, trying next backend: %s", exc)

    # 2) Google Drive (off-machine, fetchable direct link) - fallback
    try:
        from quoteforge.automation.google_drive_client import (
            is_configured, upload_public_image)
        if is_configured():
            url = upload_public_image(p, name, mimetype)
            if url:
                out.update({"url": url, "host": "google_drive", "public": True})
                return out
    except Exception as exc:  # noqa: BLE001 - never raise; fall back to local file://
        logger.warning("Google Drive publish failed, falling back to local: %s", exc)

    # 3) Local-only fallback (not publicly fetchable)
    out.update({"url": p.as_uri(), "host": "local", "public": False})
    return out
