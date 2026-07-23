"""Public hosting of customer print files + local customer-folder copy kept."""
import os, tempfile
import pytest
from PIL import Image


def _img():
    p = os.path.join(tempfile.gettempdir(), "host_test.jpg")
    Image.new("RGB", (1800, 2400), (15, 61, 46)).save(p)
    return p


def test_local_fallback_returns_file_uri():
    from quoteforge.automation.file_host import publish_print_file
    r = publish_print_file(_img())
    assert r["host"] == "local" and r["url"].startswith("file:") and not r["public"]
    assert os.path.exists(r["local"])


def test_public_dir_hosting(monkeypatch, tmp_path):
    import quoteforge.config as cfg
    pubdir = tmp_path / "public"
    monkeypatch.setattr(cfg, "PUBLIC_FILE_BASE_URL", "https://cdn.example.com/files")
    monkeypatch.setattr(cfg, "PUBLIC_FILE_DIR", str(pubdir))
    from quoteforge.automation.file_host import publish_print_file
    src = _img()
    r = publish_print_file(src)
    assert r["public"] and r["host"] == "public_dir"
    name = r["url"].rsplit("/", 1)[-1]
    assert r["url"] == f"https://cdn.example.com/files/{name}"
    # file copied into the public dir, original local copy untouched
    assert (pubdir / name).exists() and os.path.exists(src)


def test_published_name_is_tokenized_and_stable(monkeypatch, tmp_path):
    # REGRESSION: published URLs must never carry the original filename (which
    # embeds order ids / customer hints and makes /files enumerable). The name
    # is the content hash: unguessable without the bytes, and stable so
    # re-publishing the same file is idempotent (no duplicate copies).
    import re
    import quoteforge.config as cfg
    pubdir = tmp_path / "public"
    monkeypatch.setattr(cfg, "PUBLIC_FILE_BASE_URL", "https://cdn.example.com/files")
    monkeypatch.setattr(cfg, "PUBLIC_FILE_DIR", str(pubdir))
    from quoteforge.automation.file_host import publish_print_file
    src = _img()
    r1 = publish_print_file(src)
    r2 = publish_print_file(src)
    name = r1["url"].rsplit("/", 1)[-1]
    assert "host_test" not in r1["url"]
    assert re.fullmatch(r"[0-9a-f]{40}\.jpg", name), name
    assert r1["url"] == r2["url"]
    assert len(list(pubdir.iterdir())) == 1      # idempotent: one copy, not two


def test_public_dir_preferred_over_drive(monkeypatch, tmp_path):
    # REGRESSION: with BOTH backends configured, the public dir must win. Drive
    # direct-download links are a fragile fallback (interstitial HTML, quota
    # errors, public-forever files) and must never silently take over just
    # because Drive creds exist for backups.
    import quoteforge.config as cfg
    from quoteforge.automation import google_drive_client as gdc
    monkeypatch.setattr(cfg, "PUBLIC_FILE_BASE_URL", "https://cdn.example.com/files")
    monkeypatch.setattr(cfg, "PUBLIC_FILE_DIR", str(tmp_path / "public"))
    monkeypatch.setattr(gdc, "is_configured", lambda: True)
    monkeypatch.setattr(gdc, "upload_public_image",
                        lambda *a, **k: "https://drive.example.com/uc?id=X")
    from quoteforge.automation.file_host import publish_print_file, active_backend
    assert active_backend()["backend"] == "public_dir"
    r = publish_print_file(_img())
    assert r["host"] == "public_dir" and "drive" not in r["url"]


def test_drive_fallback_when_no_public_dir(monkeypatch):
    # REGRESSION: Drive still works as the fallback when no public dir is set,
    # and receives the TOKENIZED name (never the original filename).
    import quoteforge.config as cfg
    from quoteforge.automation import google_drive_client as gdc
    monkeypatch.setattr(cfg, "PUBLIC_FILE_BASE_URL", "")
    monkeypatch.setattr(cfg, "PUBLIC_FILE_DIR", "")
    seen = {}

    def fake_upload(path, filename, mimetype="image/jpeg"):
        seen["name"] = filename
        return "https://drive.example.com/uc?id=X"

    monkeypatch.setattr(gdc, "is_configured", lambda: True)
    monkeypatch.setattr(gdc, "upload_public_image", fake_upload)
    from quoteforge.automation.file_host import publish_print_file
    r = publish_print_file(_img())
    assert r["host"] == "google_drive" and r["public"]
    assert "host_test" not in seen["name"] and seen["name"].endswith(".jpg")


def test_missing_file():
    from quoteforge.automation.file_host import publish_print_file
    r = publish_print_file("/no/such/file.jpg")
    assert r["url"] == "" and not r["public"]


def test_upload_keeps_local_copy_and_publishes(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    import io
    buf = io.BytesIO(); Image.new("RGB", (1800, 2400), (15, 61, 46)).save(buf, "JPEG"); buf.seek(0)
    c = app.test_client()
    r = c.post("/upload", data={"email": "buyer@x.com", "size": "8x10",
               "file": (buf, "photo.jpg")}, content_type="multipart/form-data")
    j = r.get_json()
    # Mechanics: the route publishes + returns a host + a VALID quality decision
    # (the decision now reflects the print-quality score, not a fixed approve).
    assert r.status_code == 200 and "host" in j
    assert j["decision"] in ("approve", "hold", "reject") and "quality_score" in j
