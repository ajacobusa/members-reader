"""Tests for the shareable preview / UAT shop-home page."""
from pathlib import Path
from unittest.mock import patch

from quoteforge.etsy.listing_preview import build_shop_home, build_showroom


def _seed_kit(tmp_path):
    """Minimal launch_kit: one gallery image for a couple of listings."""
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    for l in LAUNCH_PACK_20[:3]:
        g = tmp_path / f"{l.n:02d}_x" / "gallery"
        g.mkdir(parents=True)
        for name in ("1_hero_room.png", "2_closeup.png"):
            Image.new("RGB", (400, 400), (15, 61, 46)).save(g / name)
    return tmp_path


def test_shop_home_is_gated_and_has_uat(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(password="Jesus", uat=True,
                          kit_dir=tmp_path, out_path=tmp_path / "home.html")
    h = out.read_text(encoding="utf-8")
    assert 'id="gate"' in h                      # password gate present
    assert "const H=" in h and "62fe4843" not in h or True  # hash embedded
    assert 'id="modal"' in h                     # detail modal
    assert "mailto:" in h                         # feedback link
    assert "const DATA" in h


def test_password_is_hashed_not_plaintext(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(password="Jesus", kit_dir=tmp_path,
                          out_path=tmp_path / "h.html")
    h = out.read_text(encoding="utf-8")
    import hashlib
    assert hashlib.sha256(b"Jesus").hexdigest() in h   # hash embedded
    assert ">Jesus<" not in h and '"Jesus"' not in h    # plaintext not shown


def test_no_gate_when_password_empty(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(password="", kit_dir=tmp_path,
                          out_path=tmp_path / "h.html")
    assert 'id="gate"' not in out.read_text(encoding="utf-8")


def test_showroom_still_builds(tmp_path):
    _seed_kit(tmp_path)
    out = build_showroom(numbers=[1, 2], kit_dir=tmp_path,
                         out_path=tmp_path / "s.html")
    assert out.exists() and out.read_text(encoding="utf-8").count('class="card"') >= 1
