"""Off-site backup keeps exactly ONE copy in Google Drive.

upload_single_copy replaces an existing same-named file in place (and deletes any
duplicates) so the Drive folder never accumulates old snapshots."""
from unittest.mock import patch

from quoteforge.automation import google_drive_client as gdc


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _Files:
    """Records Drive files() calls so the test can assert update/delete/create."""
    def __init__(self, existing):
        self.existing = existing
        self.updated, self.deleted, self.created = [], [], []

    def list(self, **kwargs):
        return _Exec({"files": self.existing})

    def update(self, fileId, **kwargs):
        self.updated.append(fileId)
        return _Exec({"id": fileId, "webViewLink": f"http://drive/{fileId}"})

    def delete(self, fileId):
        self.deleted.append(fileId)
        return _Exec({})

    def create(self, **kwargs):
        self.created.append(kwargs)
        return _Exec({"id": "new", "webViewLink": "http://drive/new"})


class _Service:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


def _patches(files, tmp_path):
    """Patch is_configured + the google client chain to use the fake service."""
    f = tmp_path / "artifact.bin"
    f.write_bytes(b"data")
    return f, [
        patch.object(gdc, "is_configured", return_value=True),
        patch.object(gdc, "GOOGLE_DRIVE_FOLDER_ID", "FOLDER"),
        patch.object(gdc, "GOOGLE_SERVICE_ACCOUNT_FILE", "key.json"),
        patch("googleapiclient.discovery.build", return_value=_Service(files)),
        patch("googleapiclient.http.MediaFileUpload", return_value=object()),
        patch("google.oauth2.service_account.Credentials.from_service_account_file",
              return_value=object()),
    ]


def test_replaces_existing_and_dedupes(tmp_path):
    files = _Files(existing=[{"id": "f1"}, {"id": "f2"}])  # two stale copies
    f, ps = _patches(files, tmp_path)
    for p in ps:
        p.start()
    try:
        url = gdc.upload_single_copy(f, "joffiels_full_backup.bundle")
    finally:
        for p in ps:
            p.stop()
    assert files.updated == ["f1"]      # overwrote the first in place
    assert files.deleted == ["f2"]      # removed the duplicate -> exactly one left
    assert files.created == []          # did NOT add a new accumulating copy
    assert url == "http://drive/f1"


def test_creates_when_none_exists(tmp_path):
    files = _Files(existing=[])
    f, ps = _patches(files, tmp_path)
    for p in ps:
        p.start()
    try:
        url = gdc.upload_single_copy(f, "joffiels_latest_db.sqlite3")
    finally:
        for p in ps:
            p.stop()
    assert len(files.created) == 1      # first ever upload
    assert files.updated == [] and files.deleted == []
    assert url == "http://drive/new"


def test_not_configured_returns_none(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"d")
    with patch.object(gdc, "is_configured", return_value=False):
        assert gdc.upload_single_copy(f, "x") is None
