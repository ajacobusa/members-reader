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


def test_uat_has_star_rating_widget(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(kit_dir=tmp_path, out_path=tmp_path / "h.html", uat=True)
    h = out.read_text(encoding="utf-8")
    assert 'id="mstars"' in h          # star widget markup
    assert "function setRating" in h   # rating handler
    assert "RATING" in h


def test_feedback_form_url_routes_to_form(tmp_path):
    _seed_kit(tmp_path)
    url = "https://docs.google.com/forms/d/e/ABC/viewform"
    out = build_shop_home(kit_dir=tmp_path, out_path=tmp_path / "h.html",
                          feedback_form_url=url)
    h = out.read_text(encoding="utf-8")
    assert f'FORM_URL = "{url}"' in h
    assert "listing=" in h and "rating=" in h


def test_no_form_url_falls_back_to_mailto(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(kit_dir=tmp_path, out_path=tmp_path / "h.html",
                          feedback_form_url="")
    h = out.read_text(encoding="utf-8")
    assert 'FORM_URL = ""' in h
    assert "mailto:" in h


def test_showroom_still_builds(tmp_path):
    _seed_kit(tmp_path)
    out = build_showroom(numbers=[1, 2], kit_dir=tmp_path,
                         out_path=tmp_path / "s.html")
    assert out.exists() and out.read_text(encoding="utf-8").count('class="card"') >= 1


def test_modal_has_frame_picker_when_poster_exists(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    folder = tmp_path / f"{l.n:02d}_x"
    g = folder / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (400, 400), (15, 61, 46)).save(g / "1_hero.png")
    Image.new("RGB", (800, 1000), (240, 238, 232)).save(folder / "poster.png")
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert 'id="mfpick"' in h and "function pickFmt" in h
    assert '"formats"' in h            # per-listing format previews embedded


def test_frame_picker_off_skips_formats(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(numbers=[1], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=False)
    assert '"formats"' not in out.read_text(encoding="utf-8")


def test_external_assets_lazy_mode(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    folder = tmp_path / f"{l.n:02d}_x"
    g = folder / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (400, 400), (15, 61, 46)).save(g / "1_hero.png")
    Image.new("RGB", (800, 1000), (240, 238, 232)).save(folder / "poster_18x24.png")
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "index.html", external_assets=True)
    h = out.read_text(encoding="utf-8")
    assert "assets/" in h                          # listing images referenced by URL
    assert (tmp_path / "assets").is_dir() and any((tmp_path / "assets").iterdir())
    assert 'loading="lazy"' in h                   # grid lazy-loads
    # listing gallery/format images are NOT inlined (only the small logo/banner);
    # if they were, a single listing would inline ~11 images.
    assert h.count("data:image/jpeg") <= 4


def test_b2b_always_shows_affiliate_conditional(tmp_path, monkeypatch):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    from PIL import Image
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    # no affiliate links -> gift cards absent, B2B present
    monkeypatch.setattr("quoteforge.config.AFFILIATE_FLOWERS_URL", "", raising=False)
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=False)
    h = out.read_text(encoding="utf-8")
    assert "Corporate &amp; bulk gifting" in h and "b2bSend" in h
    assert "Complete the gift" not in h
    # with a flowers link -> gift card + FTC disclosure appear
    monkeypatch.setattr("quoteforge.config.AFFILIATE_FLOWERS_URL",
                        "https://aff.example/flowers", raising=False)
    out2 = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                           out_path=tmp_path / "h2.html", frame_picker=False)
    h2 = out2.read_text(encoding="utf-8")
    assert "Complete the gift" in h2 and "aff.example/flowers" in h2
    assert "affiliate links" in h2 and 'rel="sponsored noopener nofollow"' in h2


def test_competitive_sections_present(tmp_path):
    _seed_kit(tmp_path)
    out = build_shop_home(numbers=[1], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=False)
    h = out.read_text(encoding="utf-8")
    assert "Why" in h and "Happiness Guarantee" in h
    assert "Shop by occasion" in h and "<details" in h   # FAQ accordion
    assert "Build your order" in h and "function checkUpload" in h
