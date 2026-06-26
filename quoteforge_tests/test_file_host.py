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
    assert r["url"] == "https://cdn.example.com/files/host_test.jpg"
    # file copied into the public dir, original local copy untouched
    assert (pubdir / "host_test.jpg").exists() and os.path.exists(src)


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
