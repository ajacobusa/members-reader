"""Auto-map QuoteForge product families to real Gelato product UIDs.

The go-live blocker is mapping each of our ~44 product families to a real Gelato
``productUid`` (the placeholder ``GEL-*`` UIDs route to manual until then). This
module picks a sensible *representative* UID per family from the live Gelato Product
Catalog API; the variant resolver swaps colour/size at order time.

IMPORTANT: the result is a DRAFT for the owner to review. Each product should get one
test order before ``TEST_MODE`` is turned off - a representative UID can be the wrong
quality/brand, and some of our families have NO Gelato catalog at all (flagged in
``unmapped``). Network access is injected (``fetch_products``) so this is unit-testable.
"""
from __future__ import annotations

# family -> (gelato catalogUid, preference keywords). The keywords nudge the pick
# toward a sensible default within the catalog (e.g. a ceramic 11oz white mug); the
# first product is used as a fallback. None catalog => Gelato cannot fulfil it.
FAMILY_PLAN: dict[str, tuple[str | None, tuple[str, ...]]] = {
    # Mugs
    "mug:classic_mug": ("mugs", ("ceramic", "11-oz", "white")),
    "mug:color_mug": ("mugs", ("ceramic", "11-oz", "black")),
    "mug:accent_mug": ("mugs", ("ceramic", "11-oz", "black")),
    "mug:enamel_mug": ("mugs", ("enamel", "white")),
    "mug:large_mug": ("mugs", ("ceramic", "15-oz", "white")),
    "mug:xl_mug": ("mugs", ("ceramic", "20-oz", "white")),
    "mug:travel_mug": ("mugs", ("stainless", "white")),
    # Calendars
    "calendar:wall_cal": ("calendars", ("wall",)),
    "calendar:desk_cal": ("calendars", ("desk",)),
    "calendar:photo_cal": ("calendars", ("wall",)),
    "calendar:family_cal": ("calendars", ("wall",)),
    "calendar:event_cal": ("calendars", ("desk",)),
    "calendar:promo_cal": ("calendars", ("wall",)),
    "calendar:corporate_cal": ("calendars", ("wall",)),
    # Apparel (tier -> Gelato quality keyword)
    "tshirt:Value": ("t-shirts", ("crewneck", "unisex", "economy", "white")),
    "tshirt:Classic": ("t-shirts", ("crewneck", "unisex", "classic", "white")),
    "tshirt:Premium": ("t-shirts", ("crewneck", "unisex", "premium", "white")),
    "longsleeve:Value": ("t-shirts", ("long-sleeve", "economy", "white")),
    "longsleeve:Classic": ("t-shirts", ("long-sleeve", "classic", "white")),
    "longsleeve:Premium": ("t-shirts", ("long-sleeve", "premium", "white")),
    "raglan:Value": ("t-shirts", ("raglan", "economy", "white")),
    "raglan:Classic": ("t-shirts", ("raglan", "classic", "white")),
    "raglan:Premium": ("t-shirts", ("raglan", "premium", "white")),
    "tank:Value": ("tank-tops", ("economy", "white")),
    "tank:Classic": ("tank-tops", ("classic", "white")),
    "tank:Premium": ("tank-tops", ("premium", "white")),
    "polo:Value": ("polos", ("economy", "white")),
    "polo:Classic": ("polos", ("classic", "white")),
    "polo:Premium": ("polos", ("premium", "white")),
    "hoodie:Value": ("hoodies", ("economy", "white")),
    "hoodie:Classic": ("hoodies", ("classic", "white")),
    "hoodie:Premium": ("hoodies", ("premium", "white")),
    "sweatshirt:Value": ("sweatshirts", ("economy", "white")),
    "sweatshirt:Classic": ("sweatshirts", ("classic", "white")),
    "sweatshirt:Premium": ("sweatshirts", ("premium", "white")),
    # Branded
    "branded:tote": ("tote-bags", ("tote", "black")),
    "branded:bottle": ("bottles", ("stainless", "white")),
    "branded:tumbler": ("bottles", ("tumbler", "stainless")),
    "branded:notebook": ("notebooks", ("notebook",)),
    "branded:journal": ("notebooks", ("notebook",)),
    "branded:phonecase": ("phone-cases", ("iphone", "clear")),
    # Gelato has no catalog for these - not fulfillable by Gelato.
    "branded:sticker": (None, ()),
    "branded:keychain": (None, ()),
    "branded:mousepad": (None, ()),
}


def _score(uid: str, keywords: tuple[str, ...]) -> int:
    """How well a product UID matches the family's preference keywords."""
    low = (uid or "").lower()
    return sum(1 for k in keywords if k.lower() in low)


def pick_uid(products: list[dict], keywords: tuple[str, ...]) -> str:
    """Choose the product whose UID best matches the keywords (first as fallback)."""
    best, best_score = "", -1
    for p in products:
        uid = p.get("productUid") or ""
        if not uid:
            continue
        sc = _score(uid, keywords)
        if sc > best_score:
            best, best_score = uid, sc
    return best


def build_family_map(fetch_products) -> dict:
    """Build {family: gelato_uid} for every fulfillable family.

    ``fetch_products(catalog_uid) -> list[{"productUid": ...}]`` is injected so the
    function is testable without network. Returns
    ``{"map": {...}, "unmapped": [...], "by_catalog": {...}}``.
    """
    cache: dict[str, list[dict]] = {}
    out: dict[str, str] = {}
    unmapped: list[str] = []
    for family, (catalog, keywords) in FAMILY_PLAN.items():
        if not catalog:
            unmapped.append(family)
            continue
        if catalog not in cache:
            try:
                cache[catalog] = fetch_products(catalog) or []
            except Exception:  # noqa: BLE001
                cache[catalog] = []
        uid = pick_uid(cache[catalog], keywords)
        if uid:
            out[family] = uid
        else:
            unmapped.append(family)
    return {"map": out, "unmapped": unmapped,
            "mapped_count": len(out), "total": len(FAMILY_PLAN)}


def gelato_fetch_products(catalog_uid: str, limit: int = 60) -> list[dict]:
    """Live read-only fetch of a Gelato catalog's products (needs GELATO_API_KEY)."""
    import requests
    from quoteforge.config import GELATO_API_KEY
    resp = requests.post(
        f"https://product.gelatoapis.com/v3/catalogs/{catalog_uid}/products:search",
        headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
        json={"limit": limit}, timeout=30)
    resp.raise_for_status()
    return (resp.json() or {}).get("products") or []
