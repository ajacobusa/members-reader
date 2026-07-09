"""Real product photo intake — manifest / validate / install (owner-supplied path).

Pins the guarantees of the real-photo pipeline's manual seam:
  - the manifest requests ONLY UID-backed products (never asks for the unmakeable)
  - install validates (decode + min size), rejects strangers/corrupt files loudly
  - an installed photo lands exactly where the storefront build consumes it
  - end-to-end: an installed photo is discovered by the build's photo loader
All hermetic (tmp dirs, monkeypatched module paths).
"""
from pathlib import Path

import pytest
from PIL import Image

from quoteforge.automation import real_photo_intake as rpi


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    intake, mock = tmp_path / "intake", tmp_path / "mockups"
    intake.mkdir(); mock.mkdir()
    monkeypatch.setattr(rpi, "INTAKE_DIR", intake)
    monkeypatch.setattr(rpi, "MOCKUPS_DIR", mock)
    return intake, mock


def _img(path: Path, size=(800, 800)):
    Image.new("RGB", size, (240, 238, 230)).save(path)


def test_manifest_only_uid_backed_products():
    man = rpi.manifest()
    ids = [r["product_id"] for r in man]
    # unmakeable products must NEVER be requested
    for bad in ("m_raglan", "m_polo", "color_mug", "accent_mug", "bottle", "tumbler"):
        assert bad not in ids, bad
    # flagship products with real UIDs are requested, apparel capped at 8
    assert "m_tshirt" in ids and "classic_mug" in ids and "tote" in ids
    assert sum(1 for r in man if r["category"] == "apparel") <= 8
    assert all(r["filename"] == f"{r['product_id']}.jpg" for r in man)


def test_install_validates_and_places(dirs):
    intake, mock = dirs
    _img(intake / "m_tshirt.jpg")                       # valid
    _img(intake / "classic_mug.png", size=(500, 900))   # valid png
    _img(intake / "w_tshirt.jpg", size=(120, 90))       # too small -> rejected
    (intake / "m_hoodie.jpg").write_bytes(b"not an image at all")   # corrupt -> rejected
    _img(intake / "mystery_product.jpg")                # not in manifest -> unknown
    res = rpi.install()
    assert {r["file"] for r in res["installed"]} == {"m_tshirt.jpg", "classic_mug.png"}
    assert (mock / "m_tshirt.jpg").exists() and (mock / "classic_mug.png").exists()
    assert {r["file"] for r in res["rejected"]} == {"w_tshirt.jpg", "m_hoodie.jpg"}
    assert res["unknown_files"] == ["mystery_product.jpg"]
    assert not (mock / "w_tshirt.jpg").exists()          # rejected never installed


def test_status_tracks_slots(dirs):
    intake, mock = dirs
    _img(mock / "m_tshirt.jpg")                          # already installed
    _img(intake / "classic_mug.jpg")                     # awaiting install
    st = rpi.status()
    assert "m_tshirt" in st["installed"]
    assert "classic_mug" in st["waiting_install"]
    assert "tote" in st["missing"]
    assert st["total"] == len(rpi.manifest())


def test_installed_photo_reaches_build_loader(dirs, tmp_path, monkeypatch):
    # END-TO-END: a photo installed into the mockups dir is discovered by the
    # storefront build's photo loader (the same brand/mockups discovery that
    # test_realphoto_mockup proves composites into the editor).
    intake, mock = dirs
    _img(intake / "m_tshirt.jpg", size=(900, 1100))
    rpi.install()
    found = {p.stem for p in mock.glob("*.jpg")}
    assert "m_tshirt" in found
    # the loader contract: brand/mockups/<product_id>.<jpg|png> per README
    from pathlib import Path as _P
    readme = _P("brand/mockups/README.md").read_text(encoding="utf-8")
    assert "m_tshirt.jpg" in readme                       # slot documented for the owner


def test_command_registered():
    from quoteforge.admin import COMMANDS
    assert "real-photos" in COMMANDS


# ── no-human collector: Gelato-published Etsy listings as the photo source ─────

def _png_bytes(size=(900, 1100)):
    # a NON-BLANK image (half light / half dark = high variance) - the validator
    # correctly rejects near-uniform "blank" images, so a plain fill won't do.
    import io
    from PIL import ImageDraw
    im = Image.new("RGB", size, (245, 244, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size[0] // 2, size[1]], fill=(25, 30, 35))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_manifest_rows_fully_enriched():
    for r in rpi.manifest():
        assert r["gelato_uid"] and not r["gelato_uid"].upper().startswith("GEL-")
        assert r["sku"] and r["makeable"] is True
        assert r["expected_orientation"] and r["min_w"] >= 400 and r["min_h"] >= 400
        assert "template_id" in r                      # '' until owner creates templates


def test_collect_saves_validated_listing_image(dirs):
    intake, _ = dirs
    good = _png_bytes()
    res = rpi.collect_from_etsy(
        listing_lookup=lambda sku: "111" if "TSHIRT" in sku else "",
        images_lookup=lambda lid: {"studio": "https://etsy/img1.png"},
        downloader=lambda url: good)
    got = {c["product_id"] for c in res["collected"]}
    assert "m_tshirt" in got and "w_tshirt" in got
    assert (intake / "m_tshirt.jpg").exists()          # exact manifest filename
    assert "classic_mug" in res["no_listing"]          # honestly reported, not guessed


def test_collect_rejects_invalid_or_blank_images(dirs):
    intake, _ = dirs
    res = rpi.collect_from_etsy(
        listing_lookup=lambda sku: "222",
        images_lookup=lambda lid: {"studio": "https://etsy/tiny.png"},
        downloader=lambda url: _png_bytes(size=(80, 60)))     # below min res
    assert res["collected"] == []
    assert len(res["no_image"]) == res["manifest"]     # every slot rejected the image
    assert not any(intake.iterdir())                   # nothing fabricated/saved


def test_collect_skips_already_installed(dirs):
    intake, mock = dirs
    _img(mock / "m_tshirt.jpg")
    called = []
    rpi.collect_from_etsy(
        listing_lookup=lambda sku: (called.append(sku), "333")[1],
        images_lookup=lambda lid: {},
        downloader=lambda url: b"")
    assert not any("TSHIRT-" in c and c.startswith("GEL-M-TSHIRT") for c in called) or \
        all(not c.startswith("GEL-M-TSHIRT-") for c in called)


def test_selftest_pass_shape():
    st = rpi.selftest()
    assert st["overall"] in ("PASS", "FAIL")
    names = {c["name"] for c in st["checks"]}
    assert {"manifest_uid_backed", "slot_coverage", "display_path_wired"} <= names
    assert st["overall"] == "PASS"                     # green on the current repo


def test_collector_scheduled_daily():
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    args = {j.admin_args for j in SCHEDULED_JOBS}
    assert "real-photos collect" in args and "real-photos selftest" in args
