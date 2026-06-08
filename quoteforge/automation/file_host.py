"""Publish a customer print file to a public URL the print partner can fetch.

Order of preference (first that works wins):
  1. Google Drive (service account) - returns a direct-download link.
  2. A local public directory served at PUBLIC_FILE_BASE_URL - copies the file in
     and returns base_url/filename.
  3. Fallback: the local file:// URI (works in TEST_MODE / local dev only).

The LOCAL copy in the customer folder is always kept regardless - publishing only
adds an off-machine, fetchable URL. Never raises; returns a result dict.
"""
from __future__ import annotations
from pathlib import Path
import shutil

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".pdf": "application/pdf", ".tif": "image/tiff", ".tiff": "image/tiff"}


def active_backend() -> dict:
    """Which hosting backend would be used right now (without uploading anything).
    Returns {backend, public, detail}."""
    try:
        from quoteforge.automation.google_drive_client import is_configured
        if is_configured():
            return {"backend": "google_drive", "public": True,
                    "detail": "Google Drive (direct-download links)"}
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.config import PUBLIC_FILE_BASE_URL, PUBLIC_FILE_DIR
        if PUBLIC_FILE_BASE_URL and PUBLIC_FILE_DIR:
            return {"backend": "public_dir", "public": True,
                    "detail": f"public dir -> {PUBLIC_FILE_BASE_URL}"}
    except Exception:  # noqa: BLE001
        pass
    return {"backend": "local", "public": False,
            "detail": "local file:// only (not fetchable by Gelato - set Drive or "
                      "PUBLIC_FILE_DIR before go-live)"}


def publish_print_file(local_path) -> dict:
    """Return {url, host, public, local}. `local` is always the kept local copy."""
    p = Path(local_path)
    out = {"url": "", "host": "none", "public": False, "local": str(p)}
    if not p.exists():
        return out
    mimetype = _MIME.get(p.suffix.lower(), "application/octet-stream")

    # 1) Google Drive (off-machine, fetchable direct link)
    try:
        from quoteforge.automation.google_drive_client import (
            is_configured, upload_public_image)
        if is_configured():
            url = upload_public_image(p, p.name, mimetype)
            if url:
                out.update({"url": url, "host": "google_drive", "public": True})
                return out
    except Exception:  # noqa: BLE001
        pass

    # 2) Local public directory served at PUBLIC_FILE_BASE_URL
    try:
        from quoteforge.config import PUBLIC_FILE_BASE_URL, PUBLIC_FILE_DIR
        if PUBLIC_FILE_BASE_URL and PUBLIC_FILE_DIR:
            dest_dir = Path(PUBLIC_FILE_DIR)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / p.name
            if Path(dest).resolve() != p.resolve():
                shutil.copy2(p, dest)
            out.update({"url": f"{PUBLIC_FILE_BASE_URL}/{p.name}",
                        "host": "public_dir", "public": True})
            return out
    except Exception:  # noqa: BLE001
        pass

    # 3) Local-only fallback (not publicly fetchable)
    out.update({"url": p.as_uri(), "host": "local", "public": False})
    return out
