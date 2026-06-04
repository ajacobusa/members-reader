"""Tests for the full Gelato product range + one-story-to-many cross-sell."""
from quoteforge.etsy.product_lines import (
    PRODUCT_LINES, UNIVERSAL_PRODUCTS, story_to_products, bundle_value,
    catalog_by_category, top_ranked, ProductLine,
)
from quoteforge import admin


def test_product_range_is_broad():
    names = {p.name for p in PRODUCT_LINES}
    # Beyond wall art: the high-value non-print products must exist
    for must in ["Personalized Journal", "Greeting Card", "Mug 11oz", "Tote Bag",
                 "Christmas Ornament", "T-Shirt", "Photo Puzzle", "Baby Onesie",
                 "Pet Bandana", "Sticker Pack", "Mouse Pad"]:
        assert must in names


def test_every_product_is_profitable():
    for p in PRODUCT_LINES:
        assert p.net_profit > 0, f"{p.name} is not profitable"
        assert p.margin_pct > 0


def test_journals_rank_first():
    ranked = top_ranked(3)
    # Personalized journal is the #1 strategic product
    assert ranked[0].name == "Personalized Journal"


def test_story_to_products_graduation():
    bundle = story_to_products("Graduation")
    names = [p["product"] for p in bundle]
    assert "Mug 11oz" in names
    assert "T-Shirt" in names
    assert "Personalized Journal" in names
    # universal fallbacks always present
    assert "Greeting Card" in names


def test_story_to_products_memorial_uses_photo_products():
    names = [p["product"] for p in story_to_products("Pet Memorial")]
    assert "Photo Puzzle" in names or "Christmas Ornament" in names


def test_story_to_products_baby():
    names = [p["product"] for p in story_to_products("New Baby")]
    assert "Baby Onesie" in names
    assert "Baby Bib" in names


def test_universal_fallback_for_unknown_occasion():
    names = [p["product"] for p in story_to_products("Totally Unknown Occasion")]
    for u in UNIVERSAL_PRODUCTS:
        assert u in names


def test_bundle_value_totals():
    b = bundle_value("Graduation")
    assert b["product_count"] >= 4
    assert b["total_revenue"] > 0
    assert b["total_profit"] > 0
    assert b["total_profit"] < b["total_revenue"]


def test_one_story_many_products_lifts_aov():
    # A single graduation story → a bundle worth far more than one poster
    single_poster = next(p for p in PRODUCT_LINES if p.name == "Poster 18x24")
    bundle = bundle_value("Graduation")
    assert bundle["total_revenue"] > single_poster.sell_price * 2


def test_catalog_categories():
    cats = catalog_by_category()
    for c in ["paper", "drinkware", "apparel", "accessory", "seasonal", "baby", "pet"]:
        assert c in cats


# ── Cross-sell wired into the sales engine ───────────────────────

def test_upsell_action_suggests_cross_products():
    from quoteforge.etsy.sales_engine import upsell_actions
    orders = [{"order_id": "X", "status": "shipped", "upsell_sent": 0,
               "occasion": "Graduation", "sender_name": "Mom"}]
    acts = upsell_actions(orders)
    assert acts
    assert acts[0]["cross_sell_products"]  # suggests other products
    assert "matching set" in acts[0]["suggested"]


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_products_catalog(capsys):
    rc = admin.main(["products"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GELATO PRODUCT RANGE" in out
    assert "Personalized Journal" in out


def test_cli_products_bundle(capsys):
    rc = admin.main(["products", "Graduation"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ONE STORY" in out
    assert "Mug 11oz" in out
    assert "full bundle" in out
