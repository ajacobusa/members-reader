"""Storefront layout planner — a clean, expert-looking Etsy shop.

A professional Etsy storefront isn't just good listings; it's ORGANISATION. This
plans the shop SECTIONS (the left-nav categories buyers browse by), assigns each
listing to a section, recommends what to feature, and gives the storefront polish
checklist. A well-sectioned shop ranks better AND looks like a real brand.

Etsy allows up to 20 shop sections. We organise primarily by OCCASION + RECIPIENT
(how gift buyers actually shop), lead with Best Sellers, and include a Custom
section to surface the your-own-quote/photo option.
"""
from dataclasses import dataclass, field


@dataclass
class Section:
    """One Etsy shop section with the keywords that route listings into it."""
    name: str
    blurb: str                       # short note on what goes here
    match: list[str] = field(default_factory=list)  # category/occasion keywords


# The recommended section structure (ordered as they should appear).
SHOP_SECTIONS: list[Section] = [
    Section("Best Sellers", "Pin your top 3-4 proven listings here.", []),
    Section("Graduation Gifts", "All graduation + future-career pieces.",
            ["graduation", "future"]),
    Section("For Daughter", "Personalized daughter gifts.", ["daughter"]),
    Section("For Son", "Personalized son gifts.", ["son"]),
    Section("For Mom & Grandma", "Mother's Day, mom & grandma gifts.",
            ["mom", "mother", "grandma", "grandmother"]),
    Section("For Dad & Grandpa", "Father's Day, dad & grandpa gifts.",
            ["dad", "father", "grandpa", "grandfather"]),
    Section("Wedding & Anniversary", "Vows, weddings, anniversaries.",
            ["wedding", "anniversary", "wife", "husband"]),
    Section("Christian & Faith", "Faith, prayer & blessing pieces.",
            ["christian", "faith", "prayer", "blessing"]),
    Section("Memorial & Remembrance", "In-memory & pet memorial gifts.",
            ["memorial", "memory", "pet"]),
    Section("Custom Quote & Photo", "Your-own-words and add-your-photo options.",
            ["custom"]),
]


def _section_for(listing) -> str:
    """Pick the best shop section for a listing by keyword match."""
    import re
    text = f"{listing.category} {listing.occasion} {listing.title}".lower()

    def has(kw: str) -> bool:
        """Whole-word match of a keyword in the listing text."""
        # Word-boundary match so 'son' doesn't match inside 'perSONalized'.
        return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None

    # Graduation/profession wins first (highest-intent dedicated section).
    if has("graduation") or has("future"):
        return "Graduation Gifts"
    for sec in SHOP_SECTIONS:
        if sec.match and any(has(kw) for kw in sec.match):
            return sec.name
    return "Best Sellers"  # fallback


def assign_listings() -> dict:
    """Map the 20 launch listings to shop sections."""
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    sections: dict[str, list[str]] = {s.name: [] for s in SHOP_SECTIONS}
    for l in LAUNCH_PACK_20:
        sections[_section_for(l)].append(l.title)
    return sections


STOREFRONT_CHECKLIST = [
    ("Shop icon (logo)", "Square emerald/gold Joffiels logo - done"),
    ("Shop banner", "Wide branded cover with tagline - done"),
    ("Shop title + announcement", "Keyword tagline + warm announcement - done"),
    ("About / story section", "Brand story with a photo of you - add seller photo"),
    ("Shop sections", "Create the sections below and assign every listing"),
    ("Featured / Best Sellers", "Pin 3-4 top listings to the Best Sellers section"),
    ("Consistent listing photos", "Every listing uses the SAME 5-image pack "
                                   "(hero room, close-up, size chart, how-it-works, "
                                   "what's-included) for a cohesive, premium look"),
    ("Policies + FAQ", "Returns, cancellations, custom-quote/photo FAQ - done"),
    ("Cohesive titles", "All titles front-loaded + 13 tags (admin seo) - done"),
]


def shop_blueprint() -> dict:
    """The full storefront plan: sections, listing assignments, checklist."""
    return {"sections": SHOP_SECTIONS, "assignments": assign_listings(),
            "checklist": STOREFRONT_CHECKLIST}


def format_shop_text() -> str:
    """Render the storefront blueprint as printable console text."""
    bp = shop_blueprint()
    lines = ["=" * 64, "JOFFIELS STOREFRONT BLUEPRINT - expert-looking shop",
             "=" * 64, "\n## SHOP SECTIONS (create these, in order):\n"]
    for i, s in enumerate(bp["sections"], 1):
        listings = bp["assignments"].get(s.name, [])
        lines.append(f"{i:>2}. {s.name}  ({len(listings)} listing(s))")
        lines.append(f"     {s.blurb}")
        for t in listings:
            lines.append(f"        - {t}")
    lines.append("\n## STOREFRONT POLISH CHECKLIST:\n")
    for item, note in bp["checklist"]:
        lines.append(f"  [ ] {item}: {note}")
    lines.append("\nTip: a clean, well-sectioned shop with consistent photos reads")
    lines.append("as a real BRAND - it lifts trust, browse time, and conversion.")
    lines.append("=" * 64)
    return "\n".join(lines)
