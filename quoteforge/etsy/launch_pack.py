"""Lean launch strategy — start with 20 high-intent gift listings, then scale.

The mistake most sellers make: 500 generic motivation/scenery listings ("nice to
have"). The fast path: 20 PERSONALIZED gift listings aimed at buyers who are
emotional and ready to purchase this week (daughter, mom, wedding, Christian,
graduation, memorial). This module encodes that starter pack AND a phased
scaling plan so you grow into the full catalog deliberately.
"""
from dataclasses import dataclass


@dataclass
class LaunchListing:
    """One launch-pack listing: number, category, title, occasion, relationship."""
    n: int
    category: str
    title: str
    occasion: str          # maps to the personalized-message generator
    relationship: str      # who it's for


# ── Phase 1: the 20 high-converting launch listings ──────────────
LAUNCH_PACK_20: list[LaunchListing] = [
    # Daughter (4) — parents spend heavily on daughters
    LaunchListing(1,  "Daughter",   "Personalized Daughter Graduation Gift", "Graduation",   "Daughter"),
    LaunchListing(2,  "Daughter",   "Personalized Daughter Birthday Gift",   "Birthday",     "Daughter"),
    LaunchListing(3,  "Daughter",   "Personalized Daughter Christmas Gift",  "Christmas",    "Daughter"),
    LaunchListing(4,  "Daughter",   "Personalized Daughter Encouragement Gift", "Just Because", "Daughter"),
    # Son (2)
    LaunchListing(5,  "Son",        "Personalized Son Graduation Gift",      "Graduation",   "Son"),
    LaunchListing(6,  "Son",        "Personalized Son Birthday Gift",        "Birthday",     "Son"),
    # Mom (3) — massive market
    LaunchListing(7,  "Mom",        "Personalized Mother's Day Gift",        "Mother's Day", "Mother"),
    LaunchListing(8,  "Mom",        "Personalized Mom Birthday Gift",        "Birthday",     "Mother"),
    LaunchListing(9,  "Mom",        "Personalized Grandma Gift",             "Just Because", "Grandmother"),
    # Wedding / Anniversary (3) — high-spend customers
    LaunchListing(10, "Wedding",    "Personalized Wedding Vows Poster",      "Wedding",      "Wife"),
    LaunchListing(11, "Wedding",    "Personalized Anniversary Gift",         "Anniversary",  "Wife"),
    LaunchListing(12, "Wedding",    "Personalized Husband/Wife Letter",      "Just Because", "Husband"),
    # Christian (3) — your natural advantage
    LaunchListing(13, "Christian",  "Personalized Prayer For Daughter",      "Just Because", "Daughter"),
    LaunchListing(14, "Christian",  "Personalized Christian Encouragement Gift", "Just Because", "Best Friend"),
    LaunchListing(15, "Christian",  "Personalized Family Blessing Poster",   "Just Because", "Family"),
    # Graduation career-specific (3) — premium pricing
    LaunchListing(16, "Graduation", "Future Nurse Graduation Gift",          "Graduation",   "Daughter"),
    LaunchListing(17, "Graduation", "Future Dentist Graduation Gift",        "Graduation",   "Son"),
    LaunchListing(18, "Graduation", "Future Teacher Graduation Gift",        "Graduation",   "Daughter"),
    # Memorial (2) — highly emotional
    LaunchListing(19, "Memorial",   "Personalized Pet Memorial",             "Memorial / In Memory Of", "Pet"),
    LaunchListing(20, "Memorial",   "Personalized Memorial For Loved One",   "Memorial / In Memory Of", "Family"),
]

# The six proven high-converting categories to expand within FIRST
PROVEN_CATEGORIES = ["Daughter", "Mom", "Wedding", "Christian", "Graduation", "Memorial", "Son"]

# Pricing ladder (USD) — same design, sold at multiple price points.
# Low ends are set so each physical format clears a 60% net margin after
# Gelato + Etsy fees (digital has ~no unit cost, so it runs far above 60%).
PRICING = {
    "Digital Download": (19, 29),
    "Poster": (37, 59),
    "Framed Poster": (93, 129),
    "Canvas": (106, 169),
}

# What to AVOID at launch (crowded, price-sensitive, low intent)
AVOID_INITIALLY = [
    "Generic motivation", "Generic scenery", "Abstract art",
    "Quotes with no personalization", "Random holidays",
    "Phone cases", "Stickers", "T-shirts",
]

# ── Phased scaling plan (provision to grow deliberately) ─────────
SCALING_PHASES = [
    {"phase": 1, "target_listings": 20,  "focus": "Launch pack — proven gift categories, validate demand"},
    {"phase": 2, "target_listings": 50,  "focus": "Deepen the 6 proven categories (more relationships/occasions)"},
    {"phase": 3, "target_listings": 100, "focus": "Add healthcare/teacher professions + more graduation niches"},
    {"phase": 4, "target_listings": 300, "focus": "Full occasion calendar + seasonal campaigns 4-8 wks early"},
    {"phase": 5, "target_listings": 500, "focus": "Cross-sell products (mug/journal/card) for top sellers"},
    {"phase": 6, "target_listings": 2000,"focus": "Multiple shops, VAs, evergreen + every-even-year civic"},
]


def current_phase(listing_count: int) -> dict:
    """Which scaling phase a given catalog size is in."""
    for p in SCALING_PHASES:
        if listing_count <= p["target_listings"]:
            return p
    return SCALING_PHASES[-1]


def next_additions(current_count: int, batch: int = 10) -> list[dict]:
    """Suggest the next listings to add as you scale — proven categories first,
    then broadening into the wider taxonomy. Deterministic, ready to build.
    """
    from quoteforge.etsy.occasions import (
        RELATIONSHIPS, PROFESSIONS, get_month_occasions,
    )
    # Build a deep pool: proven relationships × strong occasions, then professions
    strong_occasions = ["Graduation", "Birthday", "Christmas", "Mother's Day",
                        "Father's Day", "Anniversary", "Just Because",
                        "Memorial / In Memory Of"]
    # Occasions only valid for specific relationships (no "Son Mother's Day Gift").
    _occ_only = {
        "Mother's Day": {"Mother", "Grandmother", "Wife"},
        "Father's Day": {"Father", "Grandfather", "Husband"},
        "Anniversary": {"Wife", "Husband"},
    }

    def _ok(rel: str, occ: str) -> bool:
        """True if the occasion makes sense for this relationship."""
        allowed = _occ_only.get(occ)
        return allowed is None or rel in allowed

    pool: list[dict] = []
    # 1) proven relationships across COMPATIBLE strong occasions
    for rel in ["Daughter", "Son", "Mother", "Father", "Grandmother",
                "Grandfather", "Wife", "Husband", "Best Friend", "Sister", "Brother"]:
        for occ in strong_occasions:
            if not _ok(rel, occ):
                continue
            pool.append({"title": f"Personalized {rel} {occ} Gift",
                         "relationship": rel, "occasion": occ, "tier": "proven"})
    # 2) career-specific (premium)
    for prof in PROFESSIONS:
        pool.append({"title": f"Future {prof} Graduation Gift",
                     "relationship": "Daughter", "occasion": "Graduation",
                     "tier": "profession"})
    # Skip the ones already in the launch pack
    launched = {l.title for l in LAUNCH_PACK_20}
    pool = [p for p in pool if p["title"] not in launched]
    # Return the next `batch` after the current count (relative to the 20 starter)
    start = max(0, current_count - len(LAUNCH_PACK_20))
    return pool[start:start + batch]


def launch_summary() -> dict:
    """Snapshot of the launch strategy: pack size, categories, pricing, phases."""
    return {
        "starter_listings": len(LAUNCH_PACK_20),
        "categories": sorted({l.category for l in LAUNCH_PACK_20}),
        "pricing": PRICING,
        "avoid": AVOID_INITIALLY,
        "phases": SCALING_PHASES,
    }
