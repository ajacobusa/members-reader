"""Tests for the hero collage builder + Ask Ange API wiring."""


def test_collage_builds_with_placeholders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from quoteforge.images.collage import build_collage
    out = build_collage(size=(800, 300), slots=4)
    assert out.exists()
    from PIL import Image
    assert Image.open(out).size == (800, 300)


def test_collage_uses_source_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from PIL import Image
    src = tmp_path / "brand" / "collage_src"; src.mkdir(parents=True)
    Image.new("RGB", (400, 400), (10, 80, 40)).save(src / "dog.jpg")
    from quoteforge.images.collage import build_collage
    out = build_collage(size=(800, 300), slots=4)
    assert out.exists()


def test_ange_api_wired_in_page(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.ASK_ANGE_API_URL",
                        "https://api.example/ask", raising=False)
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=False)
    h = out.read_text(encoding="utf-8")
    assert 'ANGE_API = "https://api.example/ask"' in h and "fetch(ANGE_API" in h


def test_expanded_kb_has_pet_and_subscription():
    from quoteforge.ai.ange import answer
    assert answer("do you make a pet memorial portrait")["matched"]
    assert answer("do you offer a subscription membership")["matched"]


def test_collage_command_registered():
    from quoteforge import admin
    assert "collage" in admin.COMMANDS
