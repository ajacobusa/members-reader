"""Social proof (real-data only) + customer gallery + room designer presence."""


def test_social_proof_empty_when_no_data(monkeypatch):
    import quoteforge.etsy.social_proof as sp
    monkeypatch.setattr(sp, "social_proof_stats",
                        lambda: {"orders": 0, "subscribers": 0, "reviews": 0, "avg": 0.0})
    assert sp.social_proof_bar() == ""


def test_social_proof_shows_real_counts(monkeypatch):
    import quoteforge.etsy.social_proof as sp
    monkeypatch.setattr(sp, "social_proof_stats",
                        lambda: {"orders": 42, "subscribers": 120, "reviews": 3, "avg": 4.7})
    html = sp.social_proof_bar()
    assert "42" in html and "4.7" in html and "120" in html and "sproof" in html


def test_social_proof_hides_weak_counts(monkeypatch):
    """Tiny volume counts ('9 pieces', '1 on the insider list') undercut trust, so
    we stay quiet until they're meaningful - but real reviews always show."""
    import quoteforge.etsy.social_proof as sp
    monkeypatch.setattr(sp, "social_proof_stats",
                        lambda: {"orders": 9, "subscribers": 1, "reviews": 2, "avg": 5.0})
    html = sp.social_proof_bar()
    assert "made-to-order pieces" not in html      # 9 is below the threshold
    assert "on the insider list" not in html       # 1 is below the threshold
    assert "verified review" in html               # real reviews still surface


def test_room_designer_and_gallery_in_page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert "Your room wall" in h and "function renderWall" in h and "SELWALL" in h
    assert "{sproof_html}" not in h and "{gallery_html}" not in h
