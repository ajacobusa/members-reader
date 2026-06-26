"""Layered tests for the print-quality pipeline (per the QA plan):

  1. unit-test each rule (DPI, blur, noise, compression, exposure, score)
  2. a generated fixture photo library (one per real-world failure mode)
  3. product-specific effective-DPI (same photo, different Gelato sizes)
  4. the full /upload customer flow
  5. the per-upload quality REPORT shape
  6. ANY real photos dropped into fixtures/photos/ are scored too

Fixtures are generated deterministically (no bundled binaries / no copyright); drop
real photos into quoteforge_tests/fixtures/photos/ to exercise the gate on them.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from quoteforge.images.photo_quality import (score_photo, quality_report,
                                             laplacian_variance)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "photos"


def _photo(w, h, *, blur=0.6, quality=92, bright=1.0, fmt="JPEG"):
    """A deterministic photo-like image (gradients + shapes + edges)."""
    yy, xx = np.mgrid[0:h, 0:w]
    g = (128 + 80 * np.sin(xx / w * 3.14) + 40 * np.cos(yy / h * 6.28)) * bright
    im = Image.fromarray(g.clip(0, 255).astype("uint8")).convert("RGB")
    dr = ImageDraw.Draw(im)
    for i in range(8):
        dr.ellipse([w * 0.1 * i, h * 0.08 * i, w * 0.1 * i + w * 0.3,
                    h * 0.08 * i + h * 0.3], outline=(20, 20, 20), width=6)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return im


@pytest.fixture(scope="session")
def library(tmp_path_factory):
    """Generate the test-photo library once (sized for a 16x20 poster)."""
    d = tmp_path_factory.mktemp("photos")
    cases = {}
    cases["good_300dpi"] = _photo(4800, 6000)                          # PASS
    cases["low_res_120dpi"] = _photo(1920, 2400)                       # ENHANCE (sharp, small)
    cases["blurry"] = _photo(4800, 6000, blur=6)                       # FAIL (blur)
    cases["overcompressed"] = _photo(4800, 6000, quality=8)            # FAIL (compression)
    cases["tiny"] = _photo(600, 800)                                  # FAIL (resolution)
    cases["dark"] = _photo(4800, 6000, bright=0.12)                   # WARN (exposure)
    rng = np.random.default_rng(5)
    noisy = np.asarray(_photo(5400, 7200).convert("L")).astype("float") \
        + rng.normal(0, 38, (7200, 5400))
    paths = {}
    for name, im in cases.items():
        p = d / f"{name}.jpg"
        im.save(p, "JPEG", quality=cases_quality(name))
        paths[name] = p
    pn = d / "noisy.png"
    Image.fromarray(noisy.clip(0, 255).astype("uint8")).save(pn, "PNG")
    paths["noisy"] = pn                                               # FAIL (noise)
    return paths


def cases_quality(name):
    return 8 if name == "overcompressed" else 92


# ── 1. unit tests per rule ────────────────────────────────────────────────
def test_blur_variance_sharp_beats_blurry():
    sharp = np.asarray(_photo(800, 800).convert("L"), dtype=float)
    blur = np.asarray(_photo(800, 800, blur=6).convert("L"), dtype=float)
    assert laplacian_variance(sharp) > laplacian_variance(blur) * 3


def test_score_components_present(library):
    r = score_photo(library["good_300dpi"], "16x20", run_ai=False)
    assert set(r["components"]) == {"resolution", "blur", "noise", "compression",
                                    "exposure", "ai"}


# ── 2. fixture library: each mode lands in its intended status ─────────────
@pytest.mark.parametrize("name,expected", [
    ("good_300dpi", {"PASS"}),
    ("low_res_120dpi", {"ENHANCE", "WARN"}),
    ("blurry", {"FAIL"}),
    ("overcompressed", {"FAIL"}),
    ("tiny", {"FAIL"}),
    ("noisy", {"FAIL", "WARN"}),
    ("dark", {"WARN", "FAIL"}),
])
def test_fixture_status(library, name, expected):
    r = quality_report(library[name], "16x20", run_ai=False)
    assert r["status"] in expected, f"{name} -> {r['status']} ({r['reasons']})"


# ── 3. product-specific effective DPI (the metadata-proof test) ────────────
def test_effective_dpi_depends_on_product_size(library):
    # The SAME photo passes on a small print and fails on a large one.
    photo = _photo(2400, 3000)
    p = library["good_300dpi"].parent / "psize.jpg"
    photo.save(p, "JPEG", quality=92)
    assert quality_report(p, "8x10", run_ai=False)["status"] == "PASS"     # 300 DPI
    assert quality_report(p, "24x36", run_ai=False)["status"] == "FAIL"    # ~83 DPI
    assert quality_report(p, "8x10", run_ai=False)["effective_dpi"] > \
        quality_report(p, "24x36", run_ai=False)["effective_dpi"]


# ── 4. full /upload flow: a bad photo never green-lights ───────────────────
def test_upload_flow_blocks_bad_photo(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.webhook_server import app
    import io
    buf = io.BytesIO()
    _photo(600, 800).save(buf, "JPEG", quality=20)   # tiny + compressed -> reject
    buf.seek(0)
    r = app.test_client().post("/upload", content_type="multipart/form-data",
                               data={"email": "b@x.com", "size": "16x20",
                                     "file": (buf, "bad.jpg")})
    j = r.get_json()
    # The bad photo is BLOCKED before it can reach the vendor.
    assert r.status_code == 200 and j["decision"] == "reject"
    assert j["quality_verdict"] == "reject" and "quality_message" in j


def test_upload_auto_enhances_borderline_photo(tmp_path, monkeypatch):
    # A sharp-but-undersized photo (ENHANCE) is auto-upscaled (LANCZOS now, or the
    # external AI super-res provider if configured), RE-SCORED, and only used if it
    # now passes - the buyer gets an enhanced approve without re-shooting.
    pytest.importorskip("flask")
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.webhook_server import app
    import io
    buf = io.BytesIO()
    _photo(2000, 2500).save(buf, "JPEG", quality=92)   # ~125 DPI @ 16x20, sharp
    buf.seek(0)
    r = app.test_client().post("/upload", content_type="multipart/form-data",
                               data={"email": "b@x.com", "size": "16x20",
                                     "file": (buf, "small.jpg")})
    j = r.get_json()
    assert r.status_code == 200 and j["enhanced"] is True and j["decision"] == "approve"


# ── 5. report shape (the QA report contract) ───────────────────────────────
def test_quality_report_shape(library):
    r = quality_report(library["good_300dpi"], "16x20", run_ai=False)
    for k in ("status", "action", "effective_dpi", "required_dpi", "recommended_dpi",
              "blur_score", "noise_score", "compression_score", "exposure_score",
              "face_detected", "score", "stars", "reasons", "message"):
        assert k in r, k
    assert r["status"] in ("PASS", "WARN", "ENHANCE", "FAIL")
    assert r["recommended_dpi"] >= r["required_dpi"]


def test_small_face_warns(library, monkeypatch):
    # A portrait whose face fills < 15% of the frame is flagged to crop closer.
    import quoteforge.images.photo_quality as pq
    monkeypatch.setattr(pq, "_face_fraction", lambda p: 0.06)
    r = pq.quality_report(library["good_300dpi"], "16x20", run_ai=True)
    assert "face too small in frame" in r["reasons"] and r["status"] != "PASS"
    monkeypatch.setattr(pq, "_face_fraction", lambda p: 0.40)
    assert pq.quality_report(library["good_300dpi"], "16x20", run_ai=True)["face_detected"]


def test_face_detection_degrades_safely(library):
    # The real Haar detector runs without crashing; on a non-portrait it finds no
    # face (0.0) - never None unless OpenCV is entirely unavailable.
    from quoteforge.images.photo_quality import _face_fraction
    frac = _face_fraction(library["good_300dpi"])
    assert frac is None or (0.0 <= frac <= 1.0)


def test_gate_never_raises_on_garbage(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_bytes(b"\x00\x01 not an image")
    r = quality_report(p, "16x20", run_ai=False)
    assert r["status"] == "FAIL"


# ── 7. the gate is correct for EVERY product family, not just posters ──────
@pytest.mark.parametrize("token,expect_dims", [
    ("16x20", (4800, 6000)),     # wall-art (WxH)
    ("11oz", (2220, 1025)),      # mug
    ("calendar", (2480, 3508)),  # calendar FAMILY tag (storefront sends this per month)
    ("A4", (2480, 3508)),        # calendar paper size
    ("tote", (3000, 3600)),      # branded product id
    ("branded", (3000, 3000)),   # branded family tag
    ("m_tshirt", (3600, 4800)),  # apparel garment id
    ("apparel", (3600, 4800)),   # apparel family tag
])
def test_print_dimensions_resolve_per_family(token, expect_dims):
    # REGRESSION: branded / calendar / apparel used to fall back to an 18x24 poster
    # (5400x7200) because dimensions_for only searched the wall-art catalog.
    from quoteforge.etsy.gelato_catalog import dimensions_for
    assert dimensions_for(token) == expect_dims
    assert dimensions_for(token) != (5400, 7200) or token == "16x20"


def test_calendar_photo_not_falsely_rejected(tmp_path):
    # REGRESSION: a calendar month photo is tagged size='calendar'. It used to be
    # measured against an 18x24 poster and a good 2000x2500 photo was FALSELY rejected
    # (~104 DPI). Against the real calendar page it's ~213 DPI -> accepted.
    p = tmp_path / "month.jpg"
    _photo(2000, 2500).save(p, "JPEG", quality=92)
    cal = quality_report(p, "calendar", run_ai=False)
    poster = quality_report(p, "24x36", run_ai=False)
    assert cal["effective_dpi"] > poster["effective_dpi"]      # smaller real area
    assert cal["status"] in ("PASS", "WARN", "ENHANCE")        # not FAIL


# ── 6. score any REAL photos the owner dropped into the fixtures folder ────
_real = sorted(FIXTURE_DIR.glob("*.jpg")) + sorted(FIXTURE_DIR.glob("*.png")) \
    if FIXTURE_DIR.exists() else []


@pytest.mark.skipif(not _real, reason="no real photos in fixtures/photos/")
@pytest.mark.parametrize("path", _real, ids=lambda p: p.name)
def test_real_fixture_photos_score_cleanly(path):
    r = quality_report(path, "16x20", run_ai=False)
    assert r["status"] in ("PASS", "WARN", "ENHANCE", "FAIL")
    assert isinstance(r["score"], (int, float)) and 0 <= r["score"] <= 100
