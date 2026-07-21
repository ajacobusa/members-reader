"""Tests for the AI Gift Finder + bundle builder on the page."""


def test_recommend_returns_valid():
    # Re-audit 2026-07-21 (F3): a recommended frame must be one the shop can
    # actually SELL - the classic style's aspirational Premium Solid Oak maps to
    # the fulfillable ladder (today: Classic Black Wood).
    from quoteforge.etsy.gift_finder import recommend, quiz_config
    from quoteforge.etsy.frames import available_frames
    sellable = {f.name for f in available_frames()}
    r = recommend("Graduation", "Daughter", "50to100", "classic")
    assert r["material"] == "Framed" and r["frame"] in sellable
    assert 1 <= r["listing_n"] <= 20 and r["palette"]
    cfg = quiz_config()
    assert cfg["occasions"] and cfg["relationships"] and cfg["budgets"] and cfg["styles"]


def test_recommend_budget_maps_material():
    from quoteforge.etsy.gift_finder import recommend
    assert recommend(budget="under50")["material"] == "Poster"
    assert recommend(budget="100plus")["material"] == "Acrylic"


def test_quiz_and_bundle_in_page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=False)
    h = out.read_text(encoding="utf-8")
    assert "Gift Finder" in h and "function runQuiz" in h and "const QUIZ" in h
    assert "buy a matching set" in h and "function renderBundle" in h
    assert "function toggleBundleSec" in h  # bundle is an optional, collapsible callout
