"""Tests for the 20-listing launch pack + phased scaling."""
from quoteforge.etsy.launch_pack import (
    LAUNCH_PACK_20, PROVEN_CATEGORIES, PRICING, AVOID_INITIALLY, SCALING_PHASES,
    current_phase, next_additions, launch_summary,
)
from quoteforge import admin


def test_exactly_twenty_starter_listings():
    assert len(LAUNCH_PACK_20) == 20
    # Numbered 1-20
    assert [l.n for l in LAUNCH_PACK_20] == list(range(1, 21))


def test_category_distribution_matches_strategy():
    counts = {}
    for l in LAUNCH_PACK_20:
        counts[l.category] = counts.get(l.category, 0) + 1
    assert counts["Daughter"] == 4
    assert counts["Son"] == 2
    assert counts["Mom"] == 3
    assert counts["Wedding"] == 3
    assert counts["Christian"] == 3
    assert counts["Graduation"] == 3
    assert counts["Memorial"] == 2


def test_all_listings_are_personalized():
    # The whole point: every launch listing is personalized (high intent)
    for l in LAUNCH_PACK_20:
        assert "Personalized" in l.title or "Future" in l.title


def test_pricing_ladder():
    assert PRICING["Digital Download"] == (19, 29)
    assert PRICING["Poster"] == (37, 59)
    assert PRICING["Framed Poster"] == (93, 129)
    assert PRICING["Canvas"] == (106, 169)


def test_avoid_list_has_low_intent_items():
    for item in ["Generic motivation", "Stickers", "T-shirts", "Phone cases"]:
        assert item in AVOID_INITIALLY


def test_scaling_phases_ascending():
    targets = [p["target_listings"] for p in SCALING_PHASES]
    assert targets == sorted(targets)
    assert SCALING_PHASES[0]["target_listings"] == 20  # start lean


def test_current_phase():
    assert current_phase(20)["phase"] == 1
    assert current_phase(45)["phase"] == 2
    assert current_phase(90)["phase"] == 3
    assert current_phase(9000)["phase"] == 6  # caps at last phase


def test_next_additions_are_personalized_and_new():
    adds = next_additions(20, batch=10)
    assert len(adds) == 10
    launched = {l.title for l in LAUNCH_PACK_20}
    for a in adds:
        assert "Personalized" in a["title"] or "Future" in a["title"]
        assert a["title"] not in launched  # never duplicates the starter pack


def test_next_additions_advance_with_count():
    first = next_additions(20, batch=5)
    later = next_additions(40, batch=5)
    assert first != later  # different batch as you scale


def test_proven_categories_present():
    for c in ["Daughter", "Mom", "Wedding", "Christian", "Graduation", "Memorial"]:
        assert c in PROVEN_CATEGORIES


def test_launch_summary():
    s = launch_summary()
    assert s["starter_listings"] == 20
    assert "Christmas" not in s["categories"]  # not a standalone launch category
    assert len(s["phases"]) >= 5


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_launch_shows_20(capsys):
    rc = admin.main(["launch"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "LAUNCH PACK" in out
    assert "Personalized Daughter Graduation Gift" in out
    assert "Canvas" in out
    assert "AVOID AT LAUNCH" in out


def test_cli_launch_scale(capsys):
    rc = admin.main(["launch", "scale", "20"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SCALING" in out
    assert "NEXT LISTINGS TO ADD" in out
