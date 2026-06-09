"""Storefront titles/descriptions are recipient-neutral (fit anyone)."""


def test_generalize_strips_recipients():
    from quoteforge.etsy.listing_preview import _generalize_title, _generalize_desc
    t = _generalize_title("Personalized Daughter Graduation Gift | "
                          "Graduation Gift For Daughter Wall Art | Custom Quote Print")
    assert "Daughter" not in t and "Graduation" in t and "Wall Art" in t
    assert _generalize_title("Personalized Son Birthday Gift").find("Son") == -1
    # couple gift cleanup, no stray slash
    cp = _generalize_title("Personalized Husband/Wife Letter")
    assert "/" not in cp and "Husband" not in cp and "Wife" not in cp
    # occasions are preserved
    assert "Mother's Day" in _generalize_title("Personalized Mother's Day Gift")
    # description generalized
    d = _generalize_desc("A gift for your daughter, written for your son.")
    assert "daughter" not in d.lower() and "loved one" in d.lower()


def test_all_launch_titles_generalized():
    from quoteforge.etsy.listing_preview import _generalize_title
    from quoteforge.etsy.listing_seo import build_launch_seo
    for b in build_launch_seo():
        t = _generalize_title(b.title)
        for w in ("Daughter", "Son", "Husband", "Grandma", "Grandson"):
            assert w not in t, f"{w} still in {t}"


def test_generalize_quote():
    from quoteforge.etsy.listing_preview import _generalize_quote
    assert _generalize_quote("Dear Emma, be proud. With love, Mom") == \
        "Dear [Name], be proud. With love, [Your name]"
    assert _generalize_quote("Liam, you inspire me. With love,").startswith("[Name],")
    assert _generalize_quote("Our Family, we rise.").startswith("[Name],")
    # generic wording with no name is left alone
    assert _generalize_quote("You make every day brighter.") == "You make every day brighter."


def test_no_sample_names_on_page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    nums = []
    for l in LAUNCH_PACK_20:          # render the whole pack (each needs a gallery)
        g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
        Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
        nums.append(l.n)
    from quoteforge.etsy.listing_preview import build_shop_home
    h = build_shop_home(numbers=nums, kit_dir=tmp_path,
                        out_path=tmp_path / "h.html", frame_picker=False).read_text("utf-8")
    for name in ("Emma", "Liam", "Sarah", "James", "Grace"):
        assert name not in h, f"{name} still in preview quotes"
    # ([Name] placeholder is exercised by test_generalize_quote; in TEST_MODE the
    #  preview quotes fall back to a generic, already-neutral line.)


def test_no_duplicate_titles_after_generalizing():
    from quoteforge.etsy.listing_preview import _generalize_title, _dedupe_titles
    from quoteforge.etsy.listing_seo import build_launch_seo
    listings = [{"title": _generalize_title(b.title).split(" | ")[0],
                 "full_title": _generalize_title(b.title)} for b in build_launch_seo()]
    _dedupe_titles(listings)
    titles = [e["title"] for e in listings]
    assert len(titles) == len(set(titles)), "display titles must be unique"
    # full_title stays in sync with the de-duped display title
    for e in listings:
        assert e["full_title"].startswith(e["title"]) or e["title"] in e["full_title"]


def test_no_duplicate_design_cards_on_page(tmp_path):
    """Near-duplicate designs (same concept after generalizing) are dropped, so the
    grid shows each title once - no confusing repeats."""
    import json, re
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    nums = []
    for l in LAUNCH_PACK_20:
        g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
        Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
        nums.append(l.n)
    from quoteforge.etsy.listing_preview import build_shop_home, _drop_duplicate_designs
    h = build_shop_home(numbers=nums, kit_dir=tmp_path,
                        out_path=tmp_path / "h.html", frame_picker=False).read_text("utf-8")
    data = json.loads(re.search(r'const DATA = (\[.*?\]);', h, re.S).group(1))
    titles = [d["title"] for d in data]
    assert len(titles) == len(set(titles)), "no duplicate design titles on the page"
    # distinct profession graduations are KEPT
    assert "Future Nurse Graduation Gift" in titles
    # the drop helper keeps first per title
    lst = [{"title": "A"}, {"title": "A"}, {"title": "B"}]
    _drop_duplicate_designs(lst)
    assert [x["title"] for x in lst] == ["A", "B"]
