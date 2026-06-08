"""Persistent basket + photo auto-center/zoom (AI focal point)."""
import os, tempfile
import pytest
from PIL import Image


def _page(tmp_path):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    return out.read_text(encoding="utf-8")


def test_persistent_basket_in_page(tmp_path):
    h = _page(tmp_path)
    assert 'id="basketBtn"' in h and "function renderBasket" in h
    assert "function checkout" in h and "function clearBasket" in h
    assert "function toggleBasket" in h


def test_photo_center_controls_in_page(tmp_path):
    h = _page(tmp_path)
    assert 'id="mphotoctl"' in h and "function setPhotoZoom" in h
    assert "function applyFocal" in h and "PHOTO_FX*dw" in h
    assert "d.focal" in h  # AI focal auto-applied from /upload


def test_ai_focal_point_defaults_center():
    from quoteforge.automation.print_quality import ai_focal_point
    p = os.path.join(tempfile.gettempdir(), "f.jpg")
    Image.new("RGB", (400, 400), (10, 10, 10)).save(p)
    f = ai_focal_point(p)  # TEST_MODE -> center
    assert f["x"] == 0.5 and f["y"] == 0.5


def test_ai_focal_point_pdf_center(tmp_path):
    from quoteforge.automation.print_quality import ai_focal_point
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.4")
    assert ai_focal_point(str(pdf))["x"] == 0.5


def test_upload_returns_focal(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    import io
    buf = io.BytesIO(); Image.new("RGB", (1800, 2400), (15, 61, 46)).save(buf, "JPEG"); buf.seek(0)
    r = app.test_client().post("/upload", data={"email": "b@x.com", "size": "8x10",
        "file": (buf, "p.jpg")}, content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 200 and "focal" in j and "x" in j["focal"]
