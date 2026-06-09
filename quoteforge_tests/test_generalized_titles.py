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
