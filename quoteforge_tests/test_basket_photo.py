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


def test_preview_matches_selected_size_crop(tmp_path):
    """Preview must use the selected size's aspect ratio so the crop is accurate."""
    h = _page(tmp_path)
    assert "function _printAR" in h and "function onSizeChange" in h
    assert 'id="mcrop"' in h and "Final print preview" in h
    assert 'onchange="onSizeChange()"' in h
    # aspect-fit logic present (fit framed piece to size ratio)
    assert "AW/AH > ar" in h


def test_tax_handled_at_checkout_note(tmp_path, monkeypatch):
    """Buyer tax is calculated at checkout (by the marketplace); the page must say
    so and not fabricate tax when no estimate rate is configured."""
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "ESTIMATED_TAX_RATE_PCT", 0)
    h = _page(tmp_path)
    assert "calculated at checkout" in h
    assert "const EST_TAX_PCT = 0" in h
    assert "function _taxLine" in h
    # customer-facing copy must not name the marketplace
    assert "purchase on Etsy" not in h and "check out on Etsy" not in h


def test_estimated_tax_when_rate_set(tmp_path, monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "ESTIMATED_TAX_RATE_PCT", 7.5)
    h = _page(tmp_path)
    assert "const EST_TAX_PCT = 7.5" in h


def test_room_thumbs_inline_not_new_window(tmp_path):
    """Room thumbnails open inline (lightbox), not a new browser window."""
    h = _page(tmp_path)
    assert "function viewRoom" in h and 'id="roomLight"' in h
    assert "onclick=\"viewRoom(" in h
    assert "window.open('${s}'" not in h  # no new-window for room shots


def test_add_to_basket_and_two_mode_proof(tmp_path):
    """Accept on a single design adds to basket; basket checkout = accept all."""
    h = _page(tmp_path)
    assert "function addToBasket" in h and "Add to basket" in h
    assert "function proofAccept" in h and "function addFromProof" in h
    assert "showFinalProof('item')" in h and "showFinalProof('final')" in h
    assert 'id="mbasketbar"' in h and "function pulseBasket" in h
