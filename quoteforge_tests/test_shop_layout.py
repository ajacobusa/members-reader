"""Tests for the storefront layout planner."""
from quoteforge.etsy.shop_layout import (
    SHOP_SECTIONS, assign_listings, shop_blueprint, format_shop_text, _section_for,
)
from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
from quoteforge import admin


def test_sections_within_etsy_limit():
    assert 1 <= len(SHOP_SECTIONS) <= 20
    assert SHOP_SECTIONS[0].name == "Best Sellers"


def test_every_listing_assigned_once():
    assignments = assign_listings()
    total = sum(len(v) for v in assignments.values())
    assert total == len(LAUNCH_PACK_20)        # all 20 placed, none lost


def test_personalized_does_not_false_match_son():
    # The 'PerSONalized' word-boundary bug must not route everything to 'For Son'.
    from quoteforge.etsy.launch_pack import LaunchListing
    mom = LaunchListing(0, "Mom", "Personalized Mother's Day Gift",
                        "Mother's Day", "Mother")
    assert _section_for(mom) == "For Mom & Grandma"


def test_graduation_groups_professions():
    assignments = assign_listings()
    grad = assignments["Graduation Gifts"]
    assert any("Future Nurse" in t for t in grad)
    assert any("Daughter Graduation" in t for t in grad)


def test_blueprint_has_checklist():
    bp = shop_blueprint()
    items = [i[0] for i in bp["checklist"]]
    assert "Shop sections" in items and "Consistent listing photos" in items


def test_cli_shop_plan(capsys):
    rc = admin.main(["shop-plan"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "STOREFRONT BLUEPRINT" in out and "SHOP SECTIONS" in out
