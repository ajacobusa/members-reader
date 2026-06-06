"""Tests for the listing video generator."""
from PIL import Image

from quoteforge.images.listing_video import make_listing_video, build_video_for_listing
from quoteforge import admin


def _img(path, size=(800, 800)):
    Image.new("RGB", size, (15, 61, 46)).save(path, "PNG")
    return path


def test_makes_a_real_mp4(tmp_path):
    img = _img(tmp_path / "hero.png")
    out = make_listing_video(img, tmp_path / "v.mp4", seconds=2, fps=12, size=480)
    assert out.exists()
    assert out.stat().st_size > 1000          # a real, non-empty MP4 (solid-color
                                              # test clip compresses very small)
    assert out.suffix == ".mp4"
    # it's a valid MP4 container (ftyp box near the start)
    assert b"ftyp" in out.read_bytes()[:64]


def test_build_from_listing_folder(tmp_path):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    _img(gallery / "1_hero_room.png")
    out = build_video_for_listing(tmp_path)
    assert out is not None and out.exists()


def test_no_hero_returns_none(tmp_path):
    assert build_video_for_listing(tmp_path) is None


def test_cli_listing_video(tmp_path, capsys):
    img = _img(tmp_path / "hero.png")
    rc = admin.main(["listing-video", str(img), str(tmp_path / "out.mp4")])
    out = capsys.readouterr().out
    assert rc == 0 and "Listing video saved" in out
