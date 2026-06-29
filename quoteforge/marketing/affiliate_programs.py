"""Directory of major retail/company affiliate programs + helpers.

Code cannot *apply* on your behalf (each needs your identity, tax info, and a
site review). This module gives you the apply-ready directory (where to sign up,
typical commission) and merges whatever links you've configured so the website
shows a "Complete the gift" card for each program you've joined.

Most brands are accessed through an affiliate NETWORK - join the network once,
then search the brand inside it and grab your tracking link.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

NETWORK_SIGNUP = {
    "Amazon": "https://affiliate-program.amazon.com",
    "Impact": "https://impact.com/publishers/",
    "CJ": "https://signup.cj.com/member/signup/publisher/",
    "Rakuten": "https://rakutenadvertising.com/affiliate/",
    "ShareASale": "https://www.shareasale.com/info/",
    "Awin": "https://www.awin.com/us/publishers",
    "FlexOffers": "https://www.flexoffers.com/affiliate-programs/",
}


@dataclass(frozen=True)
class Program:
    """One retail affiliate program: brand, category, network and typical commission."""
    name: str
    category: str        # flowers | giftcards | gifts | home | marketplace
    network: str         # key into NETWORK_SIGNUP
    commission: str      # typical publisher commission (approx)
    note: str = ""

    @property
    def signup_url(self) -> str:
        """Publisher signup URL for this program's affiliate network."""
        return NETWORK_SIGNUP.get(self.network, "")


# Curated catalog of major programs relevant to a personalized-gift shop.
PROGRAMS: list[Program] = [
    # ── Flowers ──
    Program("1-800-Flowers", "flowers", "CJ", "up to 10%"),
    Program("FTD", "flowers", "CJ", "~7%"),
    Program("Teleflora", "flowers", "CJ", "up to 8%"),
    Program("ProFlowers", "flowers", "CJ", "~7%"),
    Program("The Bouqs Co.", "flowers", "Impact", "8-12%"),
    Program("UrbanStems", "flowers", "ShareASale", "~12%"),
    Program("Edible Arrangements", "flowers", "CJ", "~6%"),
    Program("Harry & David", "flowers", "CJ", "up to 6%", "gourmet gift baskets"),
    # ── Gift cards ──
    Program("Raise", "giftcards", "CJ", "1-2%", "discounted gift cards"),
    Program("CardCash", "giftcards", "FlexOffers", "~1-3%"),
    Program("GiftCards.com", "giftcards", "Rakuten", "~2%"),
    # ── General gifts / personalized ──
    Program("Amazon Associates", "gifts", "Amazon", "1-10%", "direct signup; huge catalog"),
    Program("Uncommon Goods", "gifts", "CJ", "~5%", "unique gifts"),
    Program("Personalization Mall", "gifts", "CJ", "~8%", "personalized gifts"),
    Program("Minted", "gifts", "CJ", "~5%", "art + stationery"),
    Program("Etsy", "marketplace", "Awin", "~4%", "yes, Etsy has its own affiliate"),
    # ── Big-box / marketplace ──
    Program("Walmart", "marketplace", "Impact", "1-4%"),
    Program("Target", "marketplace", "Impact", "1-8%"),
    Program("Macy's", "marketplace", "Rakuten", "~2-4%"),
    # ── Home decor (adjacent to wall art) ──
    Program("Wayfair", "home", "CJ", "~5-7%"),
    Program("Pottery Barn", "home", "CJ", "~3-5%"),
    Program("Williams Sonoma", "home", "CJ", "~3-5%"),
    Program("Society6", "home", "Impact", "~varies", "art prints / decor"),
]

CATEGORY_EMOJI = {"flowers": "🌸", "giftcards": "🎁", "gifts": "✨",
                  "home": "🏡", "marketplace": "🛍️"}


def configured_links() -> dict:
    """Merge the named env links + the AFFILIATE_LINKS_JSON dict.
    Returns {label: url} for every link the owner has set (any number)."""
    import json
    from quoteforge.config import (
        AFFILIATE_FLOWERS_URL, AFFILIATE_GIFTCARD_URL, AFFILIATE_GIFTS_URL,
        AFFILIATE_LINKS_JSON,
    )
    links: dict[str, str] = {}
    if AFFILIATE_FLOWERS_URL:
        links["Fresh flowers"] = AFFILIATE_FLOWERS_URL
    if AFFILIATE_GIFTCARD_URL:
        links["Gift card"] = AFFILIATE_GIFTCARD_URL
    if AFFILIATE_GIFTS_URL:
        links["Gift ideas"] = AFFILIATE_GIFTS_URL
    if AFFILIATE_LINKS_JSON:
        try:
            extra = json.loads(AFFILIATE_LINKS_JSON)
            for k, v in extra.items():
                if v:
                    links[str(k)] = str(v)
        except Exception as exc:  # noqa: BLE001 - malformed override JSON ignored
            logger.debug("AFFILIATE_LINKS_JSON parse failed: %s", exc)
    return links


def emoji_for(label: str) -> str:
    """Best-guess emoji for a card label by matching a known program/category."""
    low = label.lower()
    for p in PROGRAMS:
        if p.name.lower() in low:
            return CATEGORY_EMOJI.get(p.category, "✨")
    for cat, emo in CATEGORY_EMOJI.items():
        if cat in low or (cat == "flowers" and "flower" in low) \
           or (cat == "giftcards" and "card" in low):
            return emo
    return "✨"


def apply_checklist() -> str:
    """A printable directory of programs to apply to, grouped by category."""
    have = configured_links()
    have_blob = " ".join(have.keys()).lower()
    order = ["flowers", "giftcards", "gifts", "marketplace", "home"]
    title = {"flowers": "FLOWERS", "giftcards": "GIFT CARDS",
             "gifts": "PERSONALIZED / GENERAL GIFTS",
             "marketplace": "BIG-BOX & MARKETPLACES", "home": "HOME DECOR"}
    lines = ["=" * 64, "AFFILIATE PROGRAMS - APPLY DIRECTORY",
             "(Join the network, then grab your link for each brand.)", "=" * 64,
             "", "NETWORKS (sign up once each):"]
    for net, url in NETWORK_SIGNUP.items():
        lines.append(f"  - {net:11} {url}")
    for cat in order:
        progs = [p for p in PROGRAMS if p.category == cat]
        if not progs:
            continue
        lines += ["", title[cat] + ":"]
        for p in progs:
            mark = "[have]" if p.name.lower() in have_blob else "[ ]   "
            extra = f" - {p.note}" if p.note else ""
            lines.append(f"  {mark} {p.name:22} via {p.network:10} "
                         f"{p.commission}{extra}")
    lines += ["", "-" * 64,
              f"Configured on your site: {len(have)} link(s).",
              "Add links to .env (AFFILIATE_* or AFFILIATE_LINKS_JSON) - each",
              "shows as a 'Complete the gift' card automatically.",
              "Reminder: use these on YOUR site/email/Pinterest, NEVER on Etsy.",
              "Disclose affiliate links (auto-added on the site) per FTC rules.",
              "=" * 64]
    return "\n".join(lines)
