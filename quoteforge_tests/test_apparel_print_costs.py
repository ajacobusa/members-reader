"""Apparel multi-area (back + sleeves) pricing is loss-proof at the target margin, and
the submission sends one file per designed area."""
import quoteforge.etsy.apparel_print_costs as pc


def _target():
    from quoteforge.config import TARGET_MARGIN_PCT, EXTRA_PRINT_MARGIN_PCT
    return TARGET_MARGIN_PCT + EXTRA_PRINT_MARGIN_PCT


def test_front_is_free_extra_area_costs():
    assert pc.area_cost("default") == 0.0 and pc.area_cost("front") == 0.0
    assert pc.area_cost("back") == 6.0
    assert pc.area_cost("sleeve-left") == 4.0 and pc.area_cost("sleeve-right") == 4.0


def test_each_extra_area_clears_target_margin_after_fees():
    # REGRESSION: the upcharge must clear the target NET margin after the marketplace
    # fee - never a loss (a flat markup would lose money once fees apply).
    for area in ("back", "sleeve-left", "sleeve-right"):
        b = pc.margin_breakdown(area)
        assert b["net_profit"] > 0                       # always profitable
        assert b["margin_pct"] >= _target() - 0.5        # hits the target margin (70%)


def test_upcharge_sums_areas_and_excludes_front():
    # front/default never adds; back + both sleeves sum their upcharges (deduped).
    assert pc.extra_print_upcharge(["front", "default"]) == 0.0
    back = pc.area_upcharge("back")
    combo = pc.extra_print_upcharge(["back", "sleeve-left", "sleeve-right", "back"])
    assert combo == round(back + 2 * pc.area_upcharge("sleeve-left"), 2)


def test_back_upcharge_matches_70pct_math():
    # back $6.00 cost, 70% target, 9.5% fee -> 6/(1-0.095-0.70)
    assert pc.area_upcharge("back") == round(6.0 / (1 - 0.095 - 0.70), 2)


def test_submission_builds_a_file_per_area():
    from quoteforge.automation.gelato_api import _build_files
    files = _build_files("http://x/front.png",
                         {"back": "http://x/back.png", "sleeve-left": "http://x/sl.png",
                          "front": "http://x/dupe.png", "sleeve-right": ""})
    types = [f["type"] for f in files]
    assert types[0] == "default"                         # front always first
    assert "back" in types and "sleeve-left" in types
    assert "front" not in types                          # front alias dropped
    assert all(f["url"] for f in files)                  # the blank sleeve-right is skipped


def test_non_http_extra_file_skipped():
    from quoteforge.automation.gelato_api import _build_files
    files = _build_files("http://x/f.png", {"back": "file:///local.png"})
    assert [f["type"] for f in files] == ["default"]     # local path never submitted
