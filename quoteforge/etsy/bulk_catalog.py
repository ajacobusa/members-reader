"""Phase 14: Bulk catalog generator.

Generates 800+ quote variations across 8 core relationships,
exports a single CSV ready for bulk Etsy listing creation.
"""
import csv
import random
from pathlib import Path

from quoteforge.config import OUTPUT_DIR, BULK_CATALOG_RELATIONSHIPS
from quoteforge.quotes.library import QUOTE_LIBRARY
from quoteforge.quotes.categories import CATEGORIES

# Maps each bulk relationship to its source category + scenery keyword
RELATIONSHIP_MAP: dict[str, dict] = {
    "Daughter": {
        "category": "Love & Relationships",
        "occasion": "Graduation Gift For Daughter",
        "scenery": "Mountains",
        "niche_title": "Personalized Daughter Gift | Custom Quote Print | Scenic Wall Art",
        "tags": "daughter gift,graduation gift,custom wall art,daughter print,mom to daughter,personalized art,mountain decor,quote poster,inspirational gift,bedroom decor,gift for her,custom quote,scenic wall art",
    },
    "Son": {
        "category": "Love & Relationships",
        "occasion": "Graduation Gift For Son",
        "scenery": "Mountains",
        "niche_title": "Personalized Son Gift | Custom Quote Print | Motivational Wall Art",
        "tags": "son gift,graduation gift,custom wall art,son print,dad to son,personalized art,mountain decor,quote poster,inspirational gift,office decor,gift for him,custom quote,scenic wall art",
    },
    "Wife": {
        "category": "Love & Relationships",
        "occasion": "Anniversary Gift",
        "scenery": "Soft Bokeh Floral",
        "niche_title": "To My Wife | Custom Love Letter Print | Anniversary Gift",
        "tags": "wife gift,anniversary gift,love letter print,custom love art,personalized vow,romantic gift,valentines day,couples gift,wedding decor,love quote,scenic love art,gift for wife,bedroom decor",
    },
    "Husband": {
        "category": "Love & Relationships",
        "occasion": "Anniversary Gift",
        "scenery": "Mountains",
        "niche_title": "To My Husband | Custom Love Letter Print | Anniversary Gift",
        "tags": "husband gift,anniversary gift,love letter print,custom love art,personalized vow,romantic gift,valentines day,couples gift,wedding decor,love quote,scenic art,gift for husband,office decor",
    },
    "Mom": {
        "category": "Love & Relationships",
        "occasion": "Mother's Day",
        "scenery": "Wildflowers",
        "niche_title": "Personalized Mom Gift | Custom Quote From Daughter Son | Mother's Day",
        "tags": "mom gift,mothers day gift,custom wall art,mom print,gift for mom,personalized art,flower decor,quote poster,heartfelt gift,bedroom decor,gift for her,custom quote,floral wall art",
    },
    "Dad": {
        "category": "Love & Relationships",
        "occasion": "Father's Day",
        "scenery": "Mountains",
        "niche_title": "Personalized Dad Gift | Custom Quote From Daughter Son | Father's Day",
        "tags": "dad gift,fathers day gift,custom wall art,dad print,gift for dad,personalized art,mountain decor,quote poster,heartfelt gift,office decor,gift for him,custom quote,scenic wall art",
    },
    "Friend": {
        "category": "Love & Relationships",
        "occasion": "Just Because",
        "scenery": "Beach & Ocean",
        "niche_title": "Best Friend Gift | Custom Friendship Quote Print | Personalized Wall Art",
        "tags": "best friend gift,friendship gift,custom wall art,friend print,bestie gift,personalized art,beach decor,quote poster,heartfelt gift,bedroom decor,gift for her,custom quote,ocean wall art",
    },
    "Graduation": {
        "category": "Life Events",
        "occasion": "Graduation",
        "scenery": "Sunrise",
        "niche_title": "Graduation Gift | Custom Quote Print | Class of 2026 Wall Art",
        "tags": "graduation gift,class of 2026,graduate gift,custom quote,motivational print,college grad,dental school,medical school,nursing grad,law school gift,achievement art,milestone gift,scenic poster",
    },
}


def generate_bulk_catalog(quotes_per_relationship: int = 100) -> Path:
    """Generate a bulk catalog CSV with quotes_per_relationship rows per relationship.

    Total rows = 8 × quotes_per_relationship (default = 800).
    Exports to OUTPUT_DIR/bulk_catalog.csv.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "bulk_catalog.csv"

    fieldnames = [
        "relationship", "quote", "occasion", "scenery",
        "etsy_title", "etsy_tags", "category", "product_notes",
    ]

    all_rows: list[dict] = []

    for rel, meta in RELATIONSHIP_MAP.items():
        cat = meta["category"]
        pool = QUOTE_LIBRARY.get(cat, [])

        # Pull from multiple related categories to hit quote_count
        extra_pools: list[str] = []
        for extra_cat in ["Motivation & Mindset", "Life Events", "Healing & Wellness",
                          "Faith & Spiritual", "Seasonal Collections"]:
            extra_pools.extend(QUOTE_LIBRARY.get(extra_cat, []))

        combined = list(set(pool + extra_pools))
        random.shuffle(combined)

        for i in range(quotes_per_relationship):
            quote = combined[i % len(combined)]
            all_rows.append({
                "relationship": rel,
                "quote": quote,
                "occasion": meta["occasion"],
                "scenery": meta["scenery"],
                "etsy_title": meta["niche_title"],
                "etsy_tags": meta["tags"],
                "category": cat,
                "product_notes": (
                    "Start with Poster 18x24. Add Canvas 16x20 and Framed 11x14 "
                    "as separate listings for higher profit."
                ),
            })

    # Backup existing before overwriting
    if csv_path.exists():
        from quoteforge.etsy.exporter import _backup_existing
        _backup_existing(csv_path)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    return csv_path


def generate_seo_pack(niche: str, count: int = 5) -> dict:
    """Generate SEO title variations, tags, and description starters for a niche.

    Returns dict with keys: titles (list), tags (list), description_starters (list).
    """
    from quoteforge.etsy.order_processor import NICHE_LISTING_TITLES, NICHE_TAGS

    titles = NICHE_LISTING_TITLES.get(niche, [
        f"Personalized {niche} | Custom Quote Print | Wall Art Gift",
    ])
    tags = NICHE_TAGS.get(niche, [
        "custom wall art", "personalized gift", "quote poster",
        "scenic print", "motivational art",
    ])
    description_starters = [
        f"Looking for the perfect personalized gift? This custom {niche.lower()} print is designed to make them feel seen, loved, and celebrated.",
        f"Every word on this print was written for one person — the special person in your life. This {niche.lower()} print is 100% personalized.",
        f"This is not just wall art. This is a message that will live on their wall and in their heart for years.",
    ]

    return {
        "niche": niche,
        "titles": titles[:count],
        "tags": tags,
        "description_starters": description_starters,
    }
