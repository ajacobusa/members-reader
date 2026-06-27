"""Subtle occasion themes: occasion key -> default {bg,text} from the EXISTING palette."""
import json

# the exact palette baked into the editor (listing_preview.py BGCOLORS / TXTCOLORS)
BGCOLORS = {"#103d2e", "#1b1b1f", "#3a2e24", "#7a2e2e", "#2e3a55", "#f4efe6", "#dcd6c8", "#c9a84c"}
TXTCOLORS = {"#f4efe6", "#ffffff", "#c9a84c", "#1b1b1f", "#103d2e", "#7a2e2e"}


def test_known_occasion_returns_its_pairing():
    from quoteforge.etsy.occasion_themes import theme_for
    assert theme_for("memorial") == {"bg": "#f4efe6", "text": "#103d2e"}
    assert theme_for("birthday") == {"bg": "#f4efe6", "text": "#c9a84c"}
    assert theme_for("wedding") == {"bg": "#f4efe6", "text": "#7a2e2e"}
    assert theme_for("father's day") == {"bg": "#3a2e24", "text": "#f4efe6"}


def test_unknown_or_empty_returns_default():
    from quoteforge.etsy.occasion_themes import theme_for
    default = {"bg": "#103d2e", "text": "#f4efe6"}
    assert theme_for("just because") == default
    assert theme_for("") == default
    assert theme_for("not-an-occasion") == default


def test_every_tint_is_in_the_existing_palette():
    # brand guard: themes may NEVER introduce an off-palette colour
    from quoteforge.etsy.occasion_themes import OCCASION_TINTS, theme_for
    for t in list(OCCASION_TINTS.values()) + [theme_for("")]:
        assert t["bg"] in BGCOLORS and t["text"] in TXTCOLORS


def test_tints_json_round_trips():
    from quoteforge.etsy.occasion_themes import tints_json, OCCASION_TINTS
    assert json.loads(tints_json()) == OCCASION_TINTS


def _page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path, out_path=tmp_path / "h.html")
    return out.read_text(encoding="utf-8")


def test_page_embeds_tint_map_and_applies_it(tmp_path):
    html = _page(tmp_path)
    assert "const OCCASION_TINT = " in html                 # map embedded
    assert '"memorial":{"bg":"#f4efe6","text":"#103d2e"}' in html
    # editor-open applies the tint from the product's occasion key
    assert "OCCASION_TINT[d.occ]" in html
