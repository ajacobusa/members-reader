"""REGRESSION: print-quality scoring gate (v2 audit / pro photo pipeline).

A blurry-but-large photo must be caught (sharpness, noise, compression, exposure +
effective DPI -> one 0-100 score with pass/warn/reject), not just an
under-resolution one. Synthetic photo-like inputs keep it deterministic + offline.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from quoteforge.images.photo_quality import score_photo, laplacian_variance


def _realistic(w, h):
    """A smooth, photo-like image (gradients + shapes + slight blur): sharp, clean."""
    yy, xx = np.mgrid[0:h, 0:w]
    g = (128 + 80 * np.sin(xx / w * 3.14) + 40 * np.cos(yy / h * 6.28))
    im = Image.fromarray(g.clip(0, 255).astype("uint8")).convert("RGB")
    dr = ImageDraw.Draw(im)
    for i in range(8):
        dr.ellipse([w * 0.1 * i, h * 0.08 * i, w * 0.1 * i + w * 0.3,
                    h * 0.08 * i + h * 0.3], outline=(20, 20, 20), width=6)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def test_good_photo_passes(tmp_path):
    p = tmp_path / "good.jpg"
    _realistic(3600, 4800).save(p, "JPEG", quality=92)
    r = score_photo(p, run_ai=False)
    assert r["verdict"] == "pass" and r["score"] >= 80 and r["stars"] == 5
    assert "soft" not in r["message"].lower()


def test_blurry_photo_is_caught(tmp_path):
    # SAME resolution as the good photo (so it's NOT a DPI failure) - only blurry.
    g = _realistic(3600, 4800).filter(ImageFilter.GaussianBlur(5))
    p = tmp_path / "blur.jpg"
    g.save(p, "JPEG", quality=92)
    r = score_photo(p, run_ai=False)
    assert r["verdict"] in ("warn", "reject")          # not a clean pass
    assert r["components"]["blur"] < 40 and r["weakest"] == "blur"


def test_tiny_photo_rejected_by_hard_resolution_gate(tmp_path):
    p = tmp_path / "tiny.jpg"
    _realistic(3600, 4800).resize((900, 1200)).save(p, "JPEG", quality=60)
    r = score_photo(p, run_ai=False)
    assert r["verdict"] == "reject"                    # ~50 DPI -> hard gate
    assert r["effective_dpi"] < 100


def test_noisy_photo_flagged(tmp_path):
    base = np.asarray(_realistic(3000, 4000).convert("L")).astype("float")
    noisy = (base + np.random.default_rng(3).normal(0, 18, base.shape)).clip(0, 255)
    p = tmp_path / "noisy.jpg"
    Image.fromarray(noisy.astype("uint8")).convert("RGB").save(p, "JPEG", quality=95)
    r = score_photo(p, run_ai=False)
    assert r["components"]["noise"] < 50               # native-scale noise detected


def test_laplacian_variance_higher_for_sharp():
    sharp = np.asarray(_realistic(800, 800).convert("L"), dtype=float)
    blurry = np.asarray(_realistic(800, 800).filter(ImageFilter.GaussianBlur(5))
                        .convert("L"), dtype=float)
    assert laplacian_variance(sharp) > laplacian_variance(blurry) * 3


def test_unreadable_image_rejected_safely(tmp_path):
    p = tmp_path / "notimg.jpg"
    p.write_text("not an image")
    r = score_photo(p, run_ai=False)
    assert r["verdict"] == "reject" and r["score"] == 0   # never raises


def test_message_never_names_a_supplier(tmp_path):
    p = tmp_path / "t.jpg"
    _realistic(900, 1200).save(p, "JPEG", quality=60)    # a rejecting case
    msg = score_photo(p, run_ai=False)["message"].lower()
    for banned in ("gelato", "printify", "printful"):
        assert banned not in msg
