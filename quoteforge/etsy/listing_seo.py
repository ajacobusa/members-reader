"""Per-listing Etsy SEO optimizer.

Etsy ranks you on how well your title + 13 tags + attributes match the exact
phrases buyers type. This turns each of the 20 launch listings into a complete,
VALIDATED, ready-to-paste SEO bundle built from the keyword database:

  - title       front-loaded with the buyer's long-tail search phrase (<=140)
  - 13 tags     multi-word long-tail phrases, each <=20 chars, all unique
  - attributes  occasion / recipient / holiday (act as extra ranking signals)
  - materials   keyword-bearing
  - description Google-optimized opener + personalization + trust + policy

Why this matters: a buyer searches "personalized daughter graduation gift", not
"art". Front-loaded long-tail phrases in the title + matching tags are what put
Joffiels on page one.
"""
from dataclasses import dataclass, field

from quoteforge.etsy.keyword_db import KEYWORD_DB

# Generic high-intent fallbacks to pad tags to exactly 13 (all <=20 chars).
_FALLBACK_TAGS = [
    "personalized gift", "custom wall art", "quote print", "gift for her",
    "gift for him", "keepsake gift", "meaningful gift", "wall decor",
    "custom quote", "heartfelt gift", "sentimental gift", "made to order",
]


@dataclass
class SeoBundle:
    listing_n: int
    category: str
    niche: str
    title: str
    tags: list[str]
    materials: list[str]
    attributes: dict
    description: str
    warnings: list[str] = field(default_factory=list)


def _resolve_niche(category: str, occasion: str, title: str) -> str:
    """Map a listing to the best keyword_db niche (relationship-aware)."""
    t = f"{title} {occasion} {category}".lower()
    # Career-specific graduation niches win first.
    if "nurse" in t: return "Future Nurse"
    if "dentist" in t or "dental" in t: return "Future Dentist"
    if "doctor" in t: return "Future Doctor"
    if "teacher" in t: return "Teacher Gift"
    if "pet" in t: return "Pet Memorial"
    # Relationship niches — most specific first (grandmother before mother).
    rel_order = [
        ("grandmother", "Grandma Gift"), ("grandma", "Grandma Gift"),
        ("grandfather", "Grandpa Gift"), ("grandpa", "Grandpa Gift"),
        ("daughter", "Daughter Gifts"), ("son", "Son Gifts"),
        ("wife", "Wife Gift"), ("husband", "Husband Gift"),
        ("mother", "Mom Gift"), ("mom", "Mom Gift"),
        ("father", "Dad Gift"), ("dad", "Dad Gift"),
        ("best friend", "Best Friend Gift"), ("friend", "Best Friend Gift"),
    ]
    import re
    for kw, niche in rel_order:
        # Word-boundary match so 'son' doesn't match inside 'PerSONalized'.
        if re.search(r"\b" + re.escape(kw) + r"\b", t):
            return niche
    # Occasion / category fallbacks.
    if "anniversary" in t: return "Anniversary Gift"
    cat = category.lower()
    return {
        "wedding": "Wedding Gift", "christian": "Christian Wall Art",
        "graduation": "Graduation Gift", "memorial": "Memorial Gift",
    }.get(cat, "Graduation Gift")


def _pick_tags(niche: str) -> tuple[list[str], list[str]]:
    """Exactly 13 unique tags <=20 chars, long-tail first. Returns (tags, warns)."""
    data = KEYWORD_DB.get(niche, {})
    pool = (data.get("long_tail", []) + data.get("high_volume", [])
            + data.get("mid_volume", []) + data.get("buyer_intent", []))
    tags: list[str] = []
    seen = set()
    for raw in pool + _FALLBACK_TAGS:
        t = raw.strip().lower()
        if len(t) <= 20 and t not in seen:
            tags.append(t); seen.add(t)
        if len(tags) == 13:
            break
    warns = []
    if len(tags) < 13:
        warns.append(f"only {len(tags)} tags available for '{niche}'")
    return tags[:13], warns


def _build_title(base_title: str, niche: str) -> str:
    """Front-load the listing title with the strongest long-tail phrase (<=140)."""
    data = KEYWORD_DB.get(niche, {})
    longtail = (data.get("long_tail") or data.get("buyer_intent") or [""])
    # Strongest phrase that adds new words and keeps us <=140.
    extra = ""
    for phrase in longtail:
        cand = f"{base_title} | {phrase.title()}"
        if len(cand) <= 120:
            extra = phrase.title()
            base_title = cand
            break
    tail = " | Custom Quote Wall Art Print"
    if len(base_title) + len(tail) <= 140:
        base_title += tail
    return base_title[:140].strip()


def _product_options_block() -> str:
    """The 'choose your product' section, built from the variation model so it
    reflects real materials, sizes, frame colors and 60%-floor entry prices."""
    from quoteforge.etsy.variations import options_block
    return options_block() + "\n"


def _build_description(listing, niche: str) -> str:
    from quoteforge.config import SHOP_NAME
    data = KEYWORD_DB.get(niche, {})
    hook_kw = (data.get("buyer_intent") or data.get("long_tail") or [""])[0]
    recipient = listing.relationship
    occ = listing.occasion
    return (
        f"A personalized {occ.lower()} gift for your {recipient.lower()}, "
        f"hand-crafted just for them - {hook_kw}.\n\n"
        f"HOW IT WORKS\n"
        f"1. Add the recipient's name, the occasion, and a short story at checkout.\n"
        f"2. We design your custom piece and send a digital PROOF for your approval.\n"
        f"3. Reply APPROVED (or request changes) - nothing prints until you're happy.\n"
        f"4. Printed on premium stock and shipped directly to you with tracking.\n\n"
        f"WHAT'S INCLUDED\n"
        f"- A one-of-a-kind, personalized design written for your {recipient.lower()}\n"
        f"- Free digital proof before printing\n"
        f"- Your chosen print, made to order on premium materials\n\n"
        f"{_product_options_block()}\n"
        f"FRAME NOT INCLUDED (unless you choose a Framed option)\n"
        f"Poster prints ship unframed and Canvas/Acrylic/Metal are frameless - "
        f"the frame shown in the photos is for display only. Want it framed? "
        f"Choose the \"Framed print\" material and your frame style at checkout "
        f"(from an Essential slim frame to Premium Oak, Walnut, or Gold).\n\n"
        f"POLICIES\n"
        f"Personalized items are made to order and final sale. If your order "
        f"arrives damaged or with a printing error, message us within 7 days "
        f"with a photo for a free replacement.\n\n"
        f"Thank you for letting {SHOP_NAME} be part of your moment."
    )


# Professions that have a hand-curated keyword_db niche (richest keywords).
_CURATED_PROFESSION_NICHE = {
    "nurse": "Future Nurse", "dentist": "Future Dentist",
    "physician": "Future Doctor", "doctor": "Future Doctor",
    "teacher": "Teacher Gift",
}


def _detect_profession(text: str) -> str:
    """Return the profession named in the text (from the taxonomy), or ''."""
    from quoteforge.etsy.occasions import PROFESSIONS
    tl = text.lower()
    # Longest match first so 'Dental Hygienist' beats 'Dentist'.
    for p in sorted(PROFESSIONS, key=len, reverse=True):
        if p.lower() in tl:
            return p
    return ""


# Short, search-friendly aliases for long profession names (keeps tags <=20).
_PROF_ALIAS = {
    "dental hygienist": "hygienist", "orthodontist": "ortho",
    "veterinarian": "vet", "police officer": "police",
    "first responder": "first responder",  # 15 chars, fits some phrasings
}


def _profession_tags(prof: str) -> list[str]:
    """Generate exactly 13 profession-specific tags (each <=20 chars, unique)
    for ANY profession, so every job field ranks for its own searches."""
    p = prof.lower()
    forms = [p]
    alias = _PROF_ALIAS.get(p)
    if alias and alias != p:
        forms.insert(0, alias)  # prefer the short alias so phrases fit
    candidates = []
    for f in forms:
        candidates += [
            f"future {f} gift", f"{f} graduation", f"{f} grad gift",
            f"{f} student gift", f"aspiring {f}", f"new {f} gift",
            f"{f} school gift", f"{f} print", f"{f} wall art",
            f"{f} gift idea", f"future {f}", f"{f} graduate", f"{f} gift",
        ]
    # Always-available generics guarantee we reach exactly 13.
    generic = ["graduation gift", "personalized gift", "custom wall art",
               "quote print", "gift for her", "gift for him", "keepsake gift",
               "grad gift idea", "new grad gift", "class of 2026",
               "grad wall art", "inspirational art", "grad keepsake"]
    out, seen = [], set()
    for c in candidates + generic:
        if len(c) <= 20 and c not in seen:
            out.append(c); seen.add(c)
        if len(out) == 13:
            break
    return out


def _profession_title(base_title: str, prof: str) -> str:
    extra = f"{prof} School Graduation Wall Art"
    cand = f"{base_title} | {extra}"
    if len(cand) > 120:
        cand = base_title
    tail = " | Custom Quote Print"
    if len(cand) + len(tail) <= 140:
        cand += tail
    return cand[:140].strip()


# Buyers search "mom"/"dad"/"grandma", not "mother"/"father"/"grandmother".
_REL_ALIAS = {"mother": "mom", "father": "dad", "grandmother": "grandma",
              "grandfather": "grandpa"}


def _occ_kw(occasion: str) -> str:
    """The keyword form of an occasion, or '' for non-specific (Just Because)."""
    o = (occasion or "").lower()
    if "mother" in o: return "mothers day"
    if "father" in o: return "fathers day"
    if "memorial" in o or "memory" in o: return "memorial"
    if "christmas" in o: return "christmas"
    if "anniversary" in o: return "anniversary"
    if "wedding" in o: return "wedding"
    if "graduation" in o: return "graduation"
    if "birthday" in o: return "birthday"
    return ""


def _relationship_tags(relationship: str, occasion: str, niche: str) -> list[str]:
    """13 tags blending the OCCASION with the relationship, then the relationship
    niche keywords, then generics — so 'Mom Birthday' actually ranks for birthday."""
    rk = _REL_ALIAS.get(relationship.lower(), relationship.lower())
    ok = _occ_kw(occasion)
    cands: list[str] = []
    if ok:
        cands += [f"{rk} {ok} gift", f"{ok} gift for {rk}", f"{rk} {ok}",
                  f"{rk} {ok} print", f"{rk} {ok} art", f"personalized {rk} {ok}"]
        if ok == "birthday":
            cands += [f"happy birthday {rk}", f"{rk} bday gift"]
    data = KEYWORD_DB.get(niche, {})
    cands += (data.get("high_volume", []) + data.get("mid_volume", [])
              + data.get("long_tail", []))
    cands += _FALLBACK_TAGS
    out, seen = [], set()
    for c in cands:
        c = c.strip().lower()
        if len(c) <= 20 and c not in seen:
            out.append(c); seen.add(c)
        if len(out) == 13:
            break
    return out


def _relationship_title(base_title: str, relationship: str, occasion: str) -> str:
    rd = _REL_ALIAS.get(relationship.lower(), relationship.lower()).title()
    ok = _occ_kw(occasion)
    extra = (f"{ok.title()} Gift For {rd} Wall Art" if ok
             else f"Personalized {rd} Keepsake Wall Art")
    cand = f"{base_title} | {extra}"
    if len(cand) > 122:
        cand = base_title
    tail = " | Custom Quote Print"
    if len(cand) + len(tail) <= 140:
        cand += tail
    return cand[:140].strip()


def optimize_listing(listing) -> SeoBundle:
    """Full SEO bundle for one LaunchListing (profession- and occasion-aware)."""
    prof = _detect_profession(f"{listing.title} {listing.occasion}")
    if prof:
        curated = _CURATED_PROFESSION_NICHE.get(prof.lower())
        if curated and curated in KEYWORD_DB:
            niche = curated
            tags, warns = _pick_tags(niche)
            title = _build_title(listing.title, niche)
        else:
            niche = f"Future {prof}"
            tags, warns = _profession_tags(prof), []
            title = _profession_title(listing.title, prof)
    else:
        niche = _resolve_niche(listing.category, listing.occasion, listing.title)
        # Blend the occasion in (birthday/christmas/etc.) so the listing ranks
        # for its actual occasion, not just the relationship.
        tags = _relationship_tags(listing.relationship, listing.occasion, niche)
        title = _relationship_title(listing.title, listing.relationship,
                                    listing.occasion)
        warns = []
    attributes = {
        "Occasion": listing.occasion,
        "Recipient": listing.relationship,
        "Holiday": ("Christmas" if "christmas" in listing.occasion.lower()
                    else "Mother's Day" if "mother" in listing.occasion.lower()
                    else "-"),
        "Craft type": "Prints",
    }
    materials = ["Premium Matte Paper", "Giclee Print", "Fade-Resistant Ink",
                 "Canvas (optional)"]
    bundle = SeoBundle(listing.n, listing.category, niche, title, tags,
                       materials, attributes, _build_description(listing, niche),
                       warns)
    bundle.warnings += validate_seo(bundle)
    return bundle


def validate_seo(bundle: SeoBundle) -> list[str]:
    """Check Etsy hard constraints. Returns a list of problems (empty = clean)."""
    problems = []
    if len(bundle.title) > 140:
        problems.append(f"title {len(bundle.title)} chars > 140")
    if len(bundle.tags) != 13:
        problems.append(f"{len(bundle.tags)} tags (need exactly 13)")
    over = [t for t in bundle.tags if len(t) > 20]
    if over:
        problems.append(f"tags over 20 chars: {over}")
    if len(set(bundle.tags)) != len(bundle.tags):
        problems.append("duplicate tags")
    return problems


def build_launch_seo() -> list[SeoBundle]:
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    return [optimize_listing(l) for l in LAUNCH_PACK_20]


def profession_seo(profession: str, relationship: str = "Daughter") -> SeoBundle:
    """SEO bundle for a 'Future {profession}' graduation listing — works for
    ANY profession, curated or not."""
    from quoteforge.etsy.launch_pack import LaunchListing
    n = 0
    listing = LaunchListing(n, "Graduation",
                            f"Future {profession} Graduation Gift",
                            "Graduation", relationship)
    return optimize_listing(listing)


def relationship_seo(relationship: str, occasion: str = "Birthday") -> SeoBundle:
    """SEO for a 'Personalized {Relationship} {Occasion} Gift' listing — any
    relationship + occasion (e.g. Dad Birthday, Grandma Christmas)."""
    from quoteforge.etsy.launch_pack import LaunchListing
    listing = LaunchListing(0, relationship,
                            f"Personalized {relationship} {occasion} Gift",
                            occasion, relationship)
    return optimize_listing(listing)


def all_profession_seo() -> list[SeoBundle]:
    """SEO for every profession in the taxonomy — verifies full coverage."""
    from quoteforge.etsy.occasions import PROFESSIONS
    return [profession_seo(p) for p in PROFESSIONS]


def format_seo_text(bundle: SeoBundle) -> str:
    lines = [
        "=" * 70,
        f"#{bundle.listing_n}  {bundle.category}  (niche: {bundle.niche})",
        "=" * 70,
        f"TITLE ({len(bundle.title)}/140):",
        f"  {bundle.title}",
        f"\nTAGS (13):  " + " | ".join(bundle.tags),
        f"\nMATERIALS:  " + ", ".join(bundle.materials),
        "\nATTRIBUTES: " + ", ".join(f"{k}: {v}" for k, v in bundle.attributes.items()),
        "\nDESCRIPTION:",
    ]
    lines += ["  " + l for l in bundle.description.splitlines()]
    if bundle.warnings:
        lines.append("\n[!] WARNINGS: " + "; ".join(bundle.warnings))
    return "\n".join(lines)


def export_seo_excel(path=None):
    """Export all 20 listings' SEO to an Excel sheet for easy copy-paste."""
    from openpyxl import Workbook
    from quoteforge.config import OUTPUT_DIR
    path = path or (OUTPUT_DIR / "joffiels_launch_seo.xlsx")
    bundles = build_launch_seo()
    wb = Workbook(); ws = wb.active; ws.title = "Launch SEO"
    ws.append(["#", "Category", "Niche", "Title", "Title len",
               "Tags (comma-sep)", "Materials", "Attributes",
               "Description", "Warnings"])
    for b in bundles:
        ws.append([b.listing_n, b.category, b.niche, b.title, len(b.title),
                   ", ".join(b.tags), ", ".join(b.materials),
                   "; ".join(f"{k}: {v}" for k, v in b.attributes.items()),
                   b.description, "; ".join(b.warnings)])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
