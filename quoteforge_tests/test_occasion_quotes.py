"""Each occasion gets its own personal, varied default wording (not templated)."""


def test_occasion_quote_mapping():
    from quoteforge.etsy.listing_preview import _listing_occasion_key, OCCASION_QUOTES
    assert _listing_occasion_key(2, "Personalized Daughter Birthday Gift", "Daughter") == "birthday"
    assert _listing_occasion_key(3, "Personalized Daughter Christmas Gift", "Daughter") == "christmas"
    assert _listing_occasion_key(8, "Personalized Mom Birthday Gift", "Mom") == "birthday"
    assert _listing_occasion_key(7, "Personalized Mother's Day Gift", "Mom") == "mother's day"
    assert _listing_occasion_key(10, "Personalized Wedding Vows Poster", "Wedding") == "wedding"
    assert _listing_occasion_key(19, "Personalized Pet Memorial", "Memorial") == "memorial"
    assert _listing_occasion_key(13, "Personalized Prayer", "Christian") == "faith"
    # every key resolves to a real, non-empty quote pool
    for n, t, c in [(1, "Graduation", "Daughter"), (11, "Anniversary", "Wedding")]:
        assert OCCASION_QUOTES.get(_listing_occasion_key(n, t, c))


def test_quotes_personal_and_varied_on_page(tmp_path):
    import json, re
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    nums = []
    for l in LAUNCH_PACK_20:
        g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
        Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
        nums.append(l.n)
    from quoteforge.etsy.listing_preview import build_shop_home
    h = build_shop_home(numbers=nums, kit_dir=tmp_path,
                        out_path=tmp_path / "h.html", frame_picker=False).read_text("utf-8")
    data = json.loads(re.search(r'const DATA = (\[.*?\]);', h, re.S).group(1))
    quotes = [d["quote"] for d in data]
    assert "Emma" not in h
    assert len(set(quotes)) >= 8          # plenty of variety, not one templated line
    assert "[Name], family, and you, [Name]" not in h  # no garbled name


def test_occasion_showcase_present(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home, OCCASION_SHOWCASE
    h = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                        out_path=tmp_path / "h.html", frame_picker=False).read_text("utf-8")
    assert 'class="occasions"' in h and 'class="ocgrid"' in h
    assert h.count('class="occard"') == len(OCCASION_SHOWCASE)
    for name, sub, *_ in OCCASION_SHOWCASE:
        # the onclick JS-escapes apostrophes (e.g. Mother's Day) so the handler
        # isn't a syntax error; match the escaped form the page actually emits.
        name_js = name.replace("\\", "\\\\").replace("'", "\\'")
        assert sub in h and f"shopByOccasion('{name_js}'" in h
    assert "ocfallback" in h  # elegant fallback when no photo provided
