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


def test_one_card_per_occasion_and_all_occasions_present(tmp_path):
    """Every print is fully personalizable, so the grid shows exactly ONE design per
    occasion (no 6 graduations / 3 birthdays) AND every showcased occasion - even
    ones the launch pack doesn't cover (Father's Day, Valentine's, New Baby,
    Housewarming) - lands on a card so its chip always works."""
    import json, re
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    nums = []
    for l in LAUNCH_PACK_20:
        g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
        Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
        nums.append(l.n)
    from quoteforge.etsy.listing_preview import build_shop_home, _CALENDAR_OCCASIONS
    h = build_shop_home(numbers=nums, kit_dir=tmp_path,
                        out_path=tmp_path / "h.html", frame_picker=False).read_text("utf-8")
    data = json.loads(re.search(r'const DATA = (\[.*?\]);', h, re.S).group(1))
    titles = [d["title"] for d in data]
    occs = [d.get("occ") for d in data]
    assert len(titles) == len(set(titles)), "no duplicate design titles on the page"
    # exactly one card per occasion key
    assert len(occs) == len(set(occs)), "exactly one design per occasion"
    # every showcased calendar occasion has a card (chip always lands on a design)
    for key, _disp in _CALENDAR_OCCASIONS:
        assert key in occs, f"missing a card for occasion '{key}'"
    # graduation collapsed to a single card (no Future Nurse/Dentist/Teacher noise)
    assert occs.count("graduation") == 1
    assert not any("Future Nurse" in t for t in titles)


def test_drop_duplicate_designs_keeps_first(tmp_path):
    from quoteforge.etsy.listing_preview import _drop_duplicate_designs
    lst = [{"title": "A"}, {"title": "A"}, {"title": "B"}]
    _drop_duplicate_designs(lst)
    assert [x["title"] for x in lst] == ["A", "B"]


def test_collapse_one_per_occasion_normalizes_and_reports_missing(tmp_path):
    from quoteforge.etsy.listing_preview import _collapse_to_one_per_occasion
    lst = [
        {"occ": "graduation", "title": "Future Nurse", "full_title": "x",
         "quote": "q", "imgs": ["a.jpg"]},
        {"occ": "graduation", "title": "Future Dentist", "full_title": "x",
         "quote": "q", "imgs": ["a.jpg"]},
        {"occ": "just because", "title": "Encouragement", "full_title": "x",
         "quote": "q", "imgs": ["a.jpg"]},
    ]
    missing = _collapse_to_one_per_occasion(lst)
    occs = [e["occ"] for e in lst]
    # graduation collapsed to one + title normalized
    assert occs.count("graduation") == 1
    grad = next(e for e in lst if e["occ"] == "graduation")
    assert grad["title"] == "Personalized Graduation Gift"
    # uncovered calendar occasions are reported back for separate synthesis
    missing_keys = [k for k, _ in missing]
    assert "new baby" in missing_keys and "housewarming" in missing_keys
    assert "graduation" not in missing_keys
