"""Product-opportunity agent: diff our sizes vs the partner's (network injected)."""

from quoteforge.automation.gelato_opportunities import (
    find_opportunities, format_opportunities, review_opportunities, our_inventory)


def test_finds_sizes_we_dont_sell_yet():
    ours = {"mug": {"11oz", "15oz"}}
    gel = {"mug": {"11-oz", "15-oz", "10-oz-slim", "17-oz-tall"}}
    res = find_opportunities(ours, gel)
    # 11oz/15oz already carried (normalised match); the two new sizes are opportunities
    assert set(res["mug"]["could_add"]) == {"10-oz-slim", "17-oz-tall"}


def test_substring_match_counts_as_already_have():
    # our '8x10' must match the partner's verbose '8x10-inch-200x250-mm' (not a gap)
    res = find_opportunities({"poster": {"8x10"}},
                             {"poster": {"8x10-inch-200x250-mm"}})
    assert "poster" not in res


def test_no_opportunities_when_in_sync():
    res = find_opportunities({"mug": {"11oz"}}, {"mug": {"11-oz"}})
    assert res == {}
    assert "matches what the partner offers" in format_opportunities(res)


def test_review_uses_injected_fetch_and_our_real_inventory():
    # inject a fetch offering a 4XL the apparel catalog doesn't carry (we now sell
    # XS-3XL, so 4XL is the opportunity size Gelato has that we don't).
    def fake_fetch(catalog, attr):
        return {"S", "M", "L", "XL", "2XL", "3XL", "4XL"} if "shirt" in catalog else set()

    res = review_opportunities(fetch_sizes=fake_fetch,
                               dept_attr={"apparel": ("t-shirts", "GarmentSize")})
    assert "4XL" in res.get("apparel", {}).get("could_add", [])


def test_our_inventory_has_real_departments():
    inv = our_inventory()
    assert "11oz" in inv.get("mug", set())
    assert inv.get("apparel")            # garment sizes present
