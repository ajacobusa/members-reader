"""Google Drive client — stores generated artwork PNGs.

Setup: Google Cloud Console → Enable Drive API → Service Account → Download JSON key
"""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")


def is_configured() -> bool:
    """Check whether the Drive folder ID and service-account key file are set."""
    return bool(GOOGLE_DRIVE_FOLDER_ID and GOOGLE_SERVICE_ACCOUNT_FILE
                and Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists())


def upload_png_to_drive(file_path: Path, filename: str) -> Optional[str]:
    """Upload a PNG file to Google Drive. Returns the shareable file URL.

    Requires: pip install google-api-python-client google-auth
    Falls back gracefully if not configured.
    """
    if not is_configured():
        return None  # silently skip — local storage is used instead

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": filename,
            "parents": [GOOGLE_DRIVE_FOLDER_ID],
        }
        media = MediaFileUpload(str(file_path), mimetype="image/png", resumable=True)
        uploaded = service.files().create(
            body=file_metadata, media_body=media, fields="id,webViewLink"
        ).execute()

        file_id = uploaded.get("id", "")
        # Make publicly viewable
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return uploaded.get("webViewLink", "")
    except ImportError:
        return None   # google-api-python-client not installed
    except Exception:
        return None


def upload_file_to_drive(file_path: Path, filename: str,
                         mimetype: str = "application/octet-stream") -> Optional[str]:
    """Upload any file (DB snapshot, git bundle) to Drive. Returns the file URL,
    or None if Drive isn't configured / the upload fails. Best-effort, never
    raises — off-site backup must never break the local backup."""
    if not is_configured():
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)
        media = MediaFileUpload(str(file_path), mimetype=mimetype, resumable=True)
        uploaded = service.files().create(
            body={"name": filename, "parents": [GOOGLE_DRIVE_FOLDER_ID]},
            media_body=media, fields="id,webViewLink",
        ).execute()
        return uploaded.get("webViewLink", "")
    except Exception:
        return None


def upload_single_copy(file_path: Path, filename: str,
                       mimetype: str = "application/octet-stream") -> Optional[str]:
    """Upload keeping ONLY ONE copy in Drive. If a file with this exact name
    already exists in the folder, its contents are REPLACED in place (and any
    duplicate copies are deleted), so the backup folder never accumulates old
    snapshots - there is always exactly one current copy. Returns the file URL,
    or None if Drive isn't configured / the upload fails. Never raises."""
    if not is_configured():
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/drive.file"])
        service = build("drive", "v3", credentials=creds)

        # Find existing copies with this name in the target folder.
        safe = filename.replace("'", "\\'")
        query = (f"name = '{safe}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents "
                 f"and trashed = false")
        existing = service.files().list(
            q=query, fields="files(id)", spaces="drive").execute().get("files", [])
        media = MediaFileUpload(str(file_path), mimetype=mimetype, resumable=True)

        if existing:
            # Overwrite the first; delete any extras so exactly one remains.
            keep_id = existing[0]["id"]
            uploaded = service.files().update(
                fileId=keep_id, media_body=media, fields="id,webViewLink").execute()
            for dup in existing[1:]:
                try:
                    service.files().delete(fileId=dup["id"]).execute()
                except Exception as exc:  # noqa: BLE001 - dedupe is best-effort
                    logger.debug("drive dedupe delete skipped: %s", exc)
            return uploaded.get("webViewLink", "")

        uploaded = service.files().create(
            body={"name": filename, "parents": [GOOGLE_DRIVE_FOLDER_ID]},
            media_body=media, fields="id,webViewLink").execute()
        return uploaded.get("webViewLink", "")
    except Exception:  # noqa: BLE001 - off-site must never break local backup
        return None


def upload_public_image(file_path: Path, filename: str,
                        mimetype: str = "image/jpeg") -> Optional[str]:
    """Upload an image, make it public, and return a DIRECT download URL that a
    print partner (Gelato) can fetch (not the webViewLink preview page).
    Returns None if Drive isn't configured / upload fails."""
    if not is_configured():
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/drive.file"])
        service = build("drive", "v3", credentials=creds)
        media = MediaFileUpload(str(file_path), mimetype=mimetype, resumable=True)
        uploaded = service.files().create(
            body={"name": filename, "parents": [GOOGLE_DRIVE_FOLDER_ID]},
            media_body=media, fields="id").execute()
        fid = uploaded.get("id", "")
        if not fid:
            return None
        service.permissions().create(
            fileId=fid, body={"type": "anyone", "role": "reader"}).execute()
        # Direct-content link (fetchable by external services), not the viewer page.
        return f"https://drive.google.com/uc?export=download&id={fid}"
    except Exception:  # noqa: BLE001
        return None


def get_google_drive_setup() -> str:
    """Return step-by-step instructions for wiring up the Drive service account."""
    return """
GOOGLE DRIVE API SETUP
======================
1. Go to console.cloud.google.com
2. Create a new project: "QuoteForge"
3. Enable the Google Drive API
4. Create a Service Account:
   IAM → Service Accounts → Create → Download JSON key
5. Share your Google Drive folder with the service account email
6. Set in config.py:
   GOOGLE_DRIVE_FOLDER_ID = "your_folder_id"  (from Drive URL)
   GOOGLE_SERVICE_ACCOUNT_FILE = "C:/path/to/service-account.json"
7. Install: pip install google-api-python-client google-auth

FALLBACK: If Google Drive is not configured, artwork is saved locally to
Desktop/QuoteForge-Output/ instead.
"""
