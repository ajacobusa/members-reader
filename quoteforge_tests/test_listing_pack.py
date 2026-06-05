"""Tests for the multi-image Etsy listing pack generator."""
from PIL import Image

from quoteforge.images import listing_pack as lp
from quoteforge.images.listing_pack import build_listing_pack, SIZE
from quoteforge import admin


def _poster(path, size=(900, 1200)):
    Image.new("RGB", size, (15, 30, 50)).save(path, "PNG")
    return path


def test_build_pack_creates_five_validated_images(tmp_path):
    poster = _poster(tmp_path / "art.png")
    report = build_listing_pack(poster, tmp_path / "pack")
    assert report["total"] == 5
    assert report["failed"] == 0
    # every file exists and is the right web size
    for r in report["images"]:
        assert r["ok"] is True
        with Image.open(r["file"]) as im:
            assert im.size == SIZE
            assert im.mode == "RGB"


def test_pack_includes_expected_filenames(tmp_path):
    poster = _poster(tmp_path / "art.png")
    report = build_listing_pack(poster, tmp_path / "pack")
    names = {r["name"] for r in report["images"]}
    assert names == {"1_hero_room.png", "2_closeup.png", "3_size_chart.png",
                     "4_how_it_works.png", "5_whats_included.png"}


def test_each_image_is_non_blank(tmp_path):
    poster = _poster(tmp_path / "art.png")
    report = build_listing_pack(poster, tmp_path / "pack")
    assert all(r["non_blank"] for r in report["images"])


def test_static_images_need_no_poster(tmp_path):
    # how_it_works and whats_included are brand graphics, independent of art.
    a = lp.how_it_works(tmp_path / "h.png")
    b = lp.whats_included(tmp_path / "w.png")
    for p in (a, b):
        with Image.open(p) as im:
            assert im.size == SIZE


def test_size_chart_handles_tall_and_wide(tmp_path):
    for size in [(600, 1500), (1500, 600), (1000, 1000)]:
        poster = _poster(tmp_path / f"a_{size[0]}.png", size)
        out = lp.size_chart(poster, tmp_path / f"sc_{size[0]}.png")
        assert out.exists()


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_listing_pack(tmp_path, capsys):
    poster = _poster(tmp_path / "art.png")
    rc = admin.main(["listing-pack", str(poster), str(tmp_path / "pack")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "LISTING IMAGE PACK" in out
    assert "5/5" in out


def test_cli_listing_pack_missing_file(capsys):
    rc = admin.main(["listing-pack", "/nope/x.png"])
    assert rc == 1
