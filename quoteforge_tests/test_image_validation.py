"""Automated image validation - evidence-based, no user approval. Deterministic PIL checks
form the score; a REQUIRED image (rank 1/2) can't auto-approve without a vision detector
confirming the product (never rubber-stamped). Isolated DB per test.
"""
import io

import pytest
from PIL import Image, ImageDraw

from quoteforge.automation import image_validation as iv


def _png(w, h, *, blank=False, seed=0):
    """A realistic-ish product image (white bg + content) or a flat blank one. `seed` varies
    the low-frequency structure (a distinct band pattern) so distinct images don't collide on
    the coarse 8x8 average-hash - as genuinely different studio/lifestyle photos wouldn't."""
    im = Image.new("RGB", (w, h), (245, 245, 245))
    if not blank:
        d = ImageDraw.Draw(im)
        bands = 2 + (seed % 5)                       # different band count -> different ahash
        for i in range(bands):
            y0 = int(h * i / bands)
            shade = 40 + (i * 37 + seed * 13) % 160
            d.rectangle([int(w * .2), y0, int(w * .8), y0 + int(h / bands * 0.7)],
                        fill=(shade, 60, 90))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    db.init_db()
    return tmp_path


# ── Per-image verdicts ───────────────────────────────────────────

def test_supporting_image_auto_approves(iso_db):
    r = iv.validate_image_bytes(_png(1600, 1800), family="apparel", rank=3)
    assert r["status"] == "AUTO_APPROVED" and r["score"] == 1.0
    assert r["classification"] == "mockup"


def test_required_image_needs_product_detection(iso_db):
    # rank 1 with NO detector -> can't confirm the product -> NEEDS_REVIEW, never approved.
    r = iv.validate_image_bytes(_png(1600, 1800), family="apparel", rank=1)
    assert r["status"] == "NEEDS_REVIEW"
    # with a detector confirming the family -> AUTO_APPROVED
    r2 = iv.validate_image_bytes(_png(1600, 1800), family="apparel", rank=1,
                                 detector=lambda d, f: "apparel")
    assert r2["status"] == "AUTO_APPROVED" and r2["classification"] == "studio"


def test_required_image_wrong_product_not_approved(iso_db):
    # the detector sees a mug on an apparel SKU -> product_detected False -> not approved.
    r = iv.validate_image_bytes(_png(1600, 1800), family="apparel", rank=1,
                                detector=lambda d, f: "mug")
    assert r["status"] != "AUTO_APPROVED" and r["checks"]["product_detected"] is False


def test_blank_and_lowres_and_broken_are_blocked(iso_db):
    assert iv.validate_image_bytes(_png(1600, 1800, blank=True), family="apparel", rank=3)["status"] == "BLOCKED"
    assert iv.validate_image_bytes(_png(400, 400), family="apparel", rank=3)["status"] == "BLOCKED"
    assert iv.validate_image_bytes(b"not an image", family="apparel", rank=3)["status"] == "BLOCKED"


def test_duplicate_is_detected(iso_db):
    img = _png(1600, 1800)
    h = iv.validate_image_bytes(img, family="apparel", rank=3)["ahash"]
    r = iv.validate_image_bytes(img, family="apparel", rank=3, seen_hashes=[h])
    assert r["checks"]["not_duplicate"] is False


def test_unreachable_lowers_score(iso_db):
    r = iv.validate_image_bytes(_png(1600, 1800), family="apparel", rank=3, reachable=False)
    assert r["checks"]["reachable"] is False and r["score"] < 1.0


# ── Orchestration + publish gate ─────────────────────────────────

def _listing():
    return [{"listing_image_id": "i1", "url_fullxfull": "u1", "rank": 1},
            {"listing_image_id": "i2", "url_fullxfull": "u2", "rank": 2},
            {"listing_image_id": "i3", "url_fullxfull": "u3", "rank": 3}]


def test_validate_synced_images_and_required_gate(iso_db):
    imgs = {"u1": _png(1600, 1800, seed=1), "u2": _png(1600, 1800, seed=2),
            "u3": _png(1600, 1800, seed=3)}
    out = iv.validate_synced_images(
        "P1", "apparel", "L1",
        fetcher=lambda lid: _listing(),
        downloader=lambda url: imgs[url],           # distinct images (not duplicates)
        detector=lambda d, f: "apparel")            # confirms product for rank 1/2
    assert out["images"] == 3 and out["required_ok"] is True
    assert iv.required_images_ok("P1") is True


def test_required_gate_blocks_when_image1_fails(iso_db):
    def dl(url):
        return _png(1600, 1800, blank=True) if url == "u1" else _png(1600, 1800, seed=int(url[-1]))
    out = iv.validate_synced_images(
        "P2", "apparel", "L2", fetcher=lambda lid: _listing(), downloader=dl,
        detector=lambda d, f: "apparel")
    assert out["required_ok"] is False              # image 1 blank -> publish blocked
    assert iv.required_images_ok("P2") is False


def test_orchestrator_no_op_without_live_or_fetcher(iso_db):
    out = iv.validate_synced_images("P3", "apparel", "L3")   # TEST_MODE, no fetcher
    assert out.get("skipped") == "not live" and out["required_ok"] is False
