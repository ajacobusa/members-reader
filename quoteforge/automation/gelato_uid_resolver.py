"""Gelato UID Resolver - discover real productUids automatically, without owner labor.

Goal: replace GEL-* placeholders by MATCHING our catalog products to real Gelato catalog
products via the Gelato product API - and NEVER guess. A match is only written to the
registry (Gate 1) when its confidence clears a conservative threshold; everything else is
reported as BLOCKED for review, not written. So the resolver can run unattended and can
only ever make the registry MORE correct, never wrong.

Grounded + honest about the seam: the exact Gelato catalog/search request+response shape
is the one thing that can't be verified without a live authorised account. `_fetch_catalog`
is therefore DEFENSIVE - it never raises, returns [] on anything unexpected, and normalises
whatever Gelato returns into a flat {uid, text, attrs} record. The matching + confidence
scoring is pure and fully tested against normalised records, so only the HTTP shape is the
live-confirm surface (mirrors gelato_variant_resolver._gelato_search_variant).

Safety: live-gated (no-op without a key / in TEST_MODE); writes go through
gelato_readiness.map_real_gelato_uid, which itself refuses a GEL-* value - so a placeholder
can never be laundered back in. Read-only against Gelato; no orders, no flag flips.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_PRODUCT_API = "https://product.gelatoapis.com/v3"

# Minimum match confidence (0..1) to AUTO-WRITE a real UID. Deliberately conservative:
# below this a match is BLOCKED (reported, never written). Tunable via env at go-live.
_DEFAULT_MIN_CONFIDENCE = 0.72

# Tokens that carry no discriminating signal when matching (drop from the overlap score).
_STOPWORDS = {"gel", "the", "a", "of", "with", "and", "print", "custom", "personalized",
              "personalised", "made", "order", "to"}

# The SIZE / CAPACITY dimension tokens. A match is DISQUALIFIED unless every such token in
# our SKU is positively present in the candidate product - so a size-agnostic (or wrong-
# size) product can never be auto-written to a size-specific SKU. This closes the wrong-
# size class: GEL-M-TSHIRT-M-WHITE (men's code 'm' collapses with size 'm') must still
# require the product to actually name size M, not clear on the type+colour tokens alone.
_DIMENSION_TOKENS = {"xs", "s", "m", "l", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl", "5xl",
                     "8oz", "11oz", "12oz", "15oz", "17oz", "20oz"}


def _norm_tokens(text: str) -> set[str]:
    """Lowercase alnum tokens of a string, minus stopwords + pure numbers-without-unit.
    Colours/sizes/types survive; noise does not."""
    toks = re.split(r"[^a-z0-9]+", str(text or "").lower())
    return {t for t in toks if t and t not in _STOPWORDS and not (t.isdigit() and len(t) > 4)}


def _live() -> bool:
    """True only when genuinely live (TEST_MODE off + a Gelato key present)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


# Catalog categories we sell - discovery fetches products only from these (keyword match
# on the Gelato catalogUid/title), so we skip the ~45 irrelevant Gelato categories.
_RELEVANT_CAT_KEYWORDS = (
    "mug", "cup", "drinkware", "bottle", "tumbler", "flask",
    "shirt", "tshirt", "t-shirt", "tee", "hoodie", "sweatshirt", "sweater",
    "tank", "longsleeve", "long-sleeve", "sleeve", "raglan", "polo", "crewneck",
    "apparel", "garment", "tote", "bag", "mousepad", "mouse-pad", "mouse pad",
    "notebook", "journal", "sticker", "phone", "case", "keychain", "calendar")


def _relevant_catalog(catalog_uid: str, title: str) -> bool:
    """True if a Gelato catalog category is one WE sell (keyword match on uid/title)."""
    hay = f"{catalog_uid} {title}".lower()
    return any(k in hay for k in _RELEVANT_CAT_KEYWORDS)


def _discovery() -> bool:
    """True when READ-ONLY discovery may run: a Gelato key is present AND the owner has
    explicitly opted in via ``QF_GELATO_DISCOVERY=1`` (the ``gelato-resolve`` command sets
    it for its run). The explicit flag is what keeps the test suite + daily infra-check
    HERMETIC - they never set it, so ``_fetch_catalog`` no-ops (returns []) and makes no
    network call, exactly as before.

    Discovery only READS Gelato's catalog and writes DRAFTS (approved_for_go_live=0) that
    still require an admin verify+approve before they reach the runtime map - it never
    routes an order, never exports, never charges. The money / routing / runtime-export
    path stays gated on _live() (TEST_MODE=false)."""
    try:
        import os
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        flag = (os.getenv("QF_GELATO_DISCOVERY") or "").strip().lower()
        return bool(GELATO_API_KEY) and flag not in ("", "0", "false", "no")
    except Exception:  # noqa: BLE001
        return False


# ── The Gelato-side records (defensive live seam) ────────────────

def _normalise_product(raw: dict) -> dict | None:
    """Flatten a Gelato catalog product record into {uid, text, attrs}. Tolerant of the
    field names Gelato may use; returns None if no usable productUid is present."""
    if not isinstance(raw, dict):
        return None
    uid = ""
    for k in ("productUid", "uid", "id", "productId"):
        v = raw.get(k)
        if isinstance(v, str) and v:
            uid = v
            break
    if not uid or uid.upper().startswith("GEL-"):   # never accept a placeholder as real
        return None
    attrs: dict = {}
    for k in ("attributes", "dimensions", "variant", "measures"):
        v = raw.get(k)
        if isinstance(v, dict):
            attrs.update({str(a): str(b) for a, b in v.items()})
    text_bits = [str(raw.get(k, "")) for k in ("title", "name", "productName",
                                               "description", "catalogUid", "category")]
    text_bits.append(uid)
    text_bits.extend(attrs.values())
    return {"uid": uid, "text": " ".join(text_bits), "attrs": attrs}


def _fetch_catalog(catalog_uid: str | None = None) -> list[dict]:
    """DEFENSIVE live seam: fetch Gelato catalog products, normalised. Never raises;
    returns [] without a key / on any unexpected shape. The exact request +
    response shape is the single thing to confirm against a live Gelato account.

    Gated on _discovery() (a key present), NOT _live(): reading the catalog is safe in
    TEST_MODE because everything it feeds writes drafts only (owner-approval-gated).

    Grounded against the real Gelato v3 API: `GET /catalogs` lists the 62 catalog
    categories (catalogUid), and `GET /catalogs/{uid}/products` lists that category's real
    products (each with a productUid + attributes). We enumerate the categories (or just
    ``catalog_uid`` if given) and page through each one's products, aggregating - never
    silently truncating (a short page is logged)."""
    if not _discovery():
        return []
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        headers = {"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"}
        if catalog_uid:
            cat_uids = [catalog_uid]
        else:
            r = requests.get(f"{_PRODUCT_API}/catalogs", headers=headers, timeout=20)
            if r.status_code != 200:
                logger.warning("gelato catalogs list -> %s", r.status_code)
                return []
            cd = r.json()
            crows = cd.get("data") if isinstance(cd, dict) else cd
            # Only fetch catalogs for categories WE actually sell (mugs, apparel, drinkware,
            # branded, calendars) - skip the ~45 irrelevant Gelato categories (wallpaper,
            # brochures, wood prints...) so discovery stays fast and on-target.
            cat_uids = [c["catalogUid"] for c in (crows or [])
                        if isinstance(c, dict) and c.get("catalogUid")
                        and _relevant_catalog(c.get("catalogUid", ""), c.get("title", ""))]
        out: list[dict] = []
        _LIMIT = 100
        for cid in cat_uids:
            try:
                offset, page = 0, 0
                while page < 40:                          # hard cap: never loop unbounded
                    pr = requests.get(f"{_PRODUCT_API}/catalogs/{cid}/products",
                                      headers=headers, params={"limit": _LIMIT, "offset": offset},
                                      timeout=30)
                    if pr.status_code != 200:
                        logger.warning("gelato products %s -> %s", cid, pr.status_code)
                        break
                    pd = pr.json()
                    rows = (pd.get("products") if isinstance(pd, dict) else pd) or []
                    out.extend(p for p in (_normalise_product(x) for x in rows
                                           if isinstance(x, dict)) if p)
                    page += 1; offset += len(rows)
                    if len(rows) < _LIMIT:                 # short page => last page (no hits needed)
                        break
                if page >= 40:                             # honest: surface a possible cap-out
                    logger.warning("gelato catalog %s: hit the 40-page cap", cid)
            except Exception as exc:  # noqa: BLE001 - one catalog must not stop the sweep
                logger.warning("gelato products fetch %s failed: %s", cid, exc)
        return out
    except Exception as exc:  # noqa: BLE001 - unverified provider shape: never crash
        logger.warning("gelato catalog fetch failed (defensive): %s", exc)
        return []


# ── Our-side items + matching ────────────────────────────────────

def _our_unmapped_items() -> list[dict]:
    """Every sellable SKU still on a placeholder, with its decoded match tokens, grouped
    by family. Reuses each catalog's own verifier (the single source of what is sellable +
    still a placeholder) - the resolver never invents a SKU list."""
    from quoteforge.automation.gelato_readiness import FAMILIES, _FAMILY_VERIFY
    import importlib
    items: list[dict] = []
    for fam in FAMILIES:
        mod_name, fn = _FAMILY_VERIFY[fam]
        try:
            v = getattr(importlib.import_module(mod_name), fn)()
        except Exception as exc:  # noqa: BLE001
            logger.debug("resolver: %s verify failed: %s", fam, exc)
            continue
        for sku in v.get("placeholders", []) or []:
            items.append({"family": fam, "sku": sku, "tokens": _sku_tokens(fam, sku)})
    return items


def _sku_tokens(family: str, sku: str) -> set[str]:
    """The discriminating tokens for one of our SKUs: the family + the SKU's own decoded
    parts (type/size/colour). E.g. GEL-M-TSHIRT-M-WHITE -> {tshirt, m, white, apparel,...}.

    Colour aliases (GELATO_COLOR_ALIASES) are SUBSTITUTED: when Gelato spells a
    colour differently (our 'Dusty Rose' is their 'dusty-pink'), requiring OUR
    tokens ('rose') would make the variant permanently unmappable. The alias swaps
    in the Gelato-side tokens so the resolver can find the real product; applied
    longest-alias-first so multi-word colours can't be half-substituted."""
    toks = _norm_tokens(sku) | _norm_tokens(family)
    try:
        from quoteforge.etsy.apparel_catalog import GELATO_COLOR_ALIASES
        for ours, gelato in sorted(GELATO_COLOR_ALIASES.items(),
                                   key=lambda kv: -len(_norm_tokens(kv[0]))):
            a = _norm_tokens(ours)
            if a and a <= toks:
                toks = (toks - a) | _norm_tokens(gelato)
    except Exception as exc:  # noqa: BLE001 - alias map absent -> plain tokens
        logger.debug("colour aliases unavailable, using plain tokens: %s", exc)
    return toks


def _product_hay(product: dict) -> set[str]:
    """All normalised tokens a candidate Gelato product exposes (text + attribute values)."""
    return _norm_tokens(product.get("text", "")) | {
        t for v in product.get("attrs", {}).values() for t in _norm_tokens(v)}


def score_match(our_tokens: set[str], product: dict) -> float:
    """Confidence 0..1 that a Gelato product matches our item: the fraction of our
    discriminating tokens present in the product's text/attrs. Anchored - if none of our
    tokens appear, score is 0 (never a coincidental partial match)."""
    if not our_tokens:
        return 0.0
    hits = our_tokens & _product_hay(product)
    return round(len(hits) / len(our_tokens), 4)


def _dimensions_confirmed(our_tokens: set[str], product_hay: set[str]) -> bool:
    """True when EVERY size/capacity dimension token in our SKU is present in the product.
    A size-specific SKU can only match a product that positively names that size - so a
    size-agnostic (or wrong-size) product is DISQUALIFIED, never guessed."""
    required = our_tokens & _DIMENSION_TOKENS
    return required <= product_hay          # empty required -> trivially True


def resolve_sku(item: dict, catalog: list[dict]) -> dict:
    """Best Gelato product for one of our items + its confidence. A product that does not
    positively confirm our SKU's size/capacity dimension is DISQUALIFIED before scoring
    (never write a wrong-size UID). Returns {sku, family, uid, confidence}."""
    best_uid, best_conf = None, 0.0
    for product in catalog:
        hay = _product_hay(product)
        if not _dimensions_confirmed(item["tokens"], hay):
            continue                        # size/capacity unconfirmed -> not eligible
        c = round(len(item["tokens"] & hay) / len(item["tokens"]), 4) if item["tokens"] else 0.0
        if c > best_conf:
            best_uid, best_conf = product["uid"], c
    return {"sku": item["sku"], "family": item["family"],
            "uid": best_uid, "confidence": best_conf}


# ── Orchestration ────────────────────────────────────────────────

def _min_confidence() -> float:
    """The auto-write confidence threshold (env-tunable at go-live)."""
    import os
    try:
        return float(os.getenv("GELATO_RESOLVER_MIN_CONFIDENCE", "") or _DEFAULT_MIN_CONFIDENCE)
    except ValueError:
        return _DEFAULT_MIN_CONFIDENCE


def resolve_all(*, apply: bool = False, min_confidence: float | None = None,
                catalog: list[dict] | None = None, catalog_uid: str | None = None) -> dict:
    """Resolve every unmapped sellable SKU against the Gelato catalog.

    apply=False (default) is a DRY RUN - reports what would be written. apply=True writes
    only matches at/above the confidence threshold to the registry (via map_real_gelato_uid,
    which still refuses a GEL-*). Everything below threshold is BLOCKED (reported, never
    written). Never raises; live-gated (empty catalog -> nothing resolved).
    """
    thr = _min_confidence() if min_confidence is None else min_confidence
    cat = _fetch_catalog(catalog_uid) if catalog is None else catalog
    items = _our_unmapped_items()
    candidates, blocked = [], []
    for it in items:
        r = resolve_sku(it, cat)
        if r["uid"] and r["confidence"] >= thr:
            candidates.append(r)
        else:
            blocked.append({**r, "reason": "below_confidence"})

    # AMBIGUITY GUARD: a real Gelato productUid maps to exactly ONE of our SKUs. If a UID
    # is claimed by >1 SKU at threshold, the token match is not discriminating enough to
    # trust EITHER - block them all (never write a UID that could be the wrong product).
    from collections import Counter
    _uid_claims = Counter(r["uid"] for r in candidates)
    resolved = [r for r in candidates if _uid_claims[r["uid"]] == 1]
    blocked += [{**r, "reason": "ambiguous_shared_uid"}
                for r in candidates if _uid_claims[r["uid"]] > 1]

    written = 0
    if apply and resolved:
        # DRAFT ONLY - the resolver never writes a go-live UID. Each match is saved as a
        # draft (approved_for_go_live=0); it reaches the runtime map only after an admin
        # verifies + approves it (admin gelato-uid verify/approve).
        from quoteforge.automation.gelato_readiness import draft_uid
        for r in resolved:
            try:
                draft_uid(r["family"], r["sku"], r["uid"], score=r["confidence"],
                          reason="token/attribute match", source="resolver")
                written += 1
            except Exception as exc:  # noqa: BLE001 - a rejected write is logged, not fatal
                logger.warning("resolver draft rejected for %s: %s", r["sku"], exc)
                blocked.append({**r, "rejected": str(exc)})

    summary = {"catalog_size": len(cat), "candidates": len(items),
               "threshold": thr, "resolved": len(resolved), "blocked": len(blocked),
               "written": written, "applied": bool(apply), "live": _live(),
               "discovery": _discovery(),
               "sample_resolved": resolved[:5], "sample_blocked": blocked[:5]}
    logger.info("gelato-resolve: catalog=%d resolved=%d blocked=%d written=%d live=%s",
                len(cat), len(resolved), len(blocked), written, _live())
    return summary


def resolver_status() -> dict:
    """A quick read of resolver readiness: is it live, how many SKUs still need a UID."""
    items = _our_unmapped_items()
    return {"live": _live(), "discovery": _discovery(), "unmapped_candidates": len(items),
            "threshold": _min_confidence()}


# ── Deterministic attribute mapping (the RIGHT tool, grounded on the real UID grammar) ──
#
# Fuzzy token-matching scores ~0 against Gelato's coded productUids
# (mug_product_msz_11-oz_mmat_ceramic-white_cl_4-0). But those UIDs are perfectly
# STRUCTURED, so we parse them into attributes and match our SKU's (size, colour) exactly -
# no guessing. A SKU either maps to a real Gelato UID or is flagged UNFULFILLABLE (Gelato
# does not offer that variant), which is a real "never sell what we can't make" guard.

# Our colour name -> Gelato colour token (as seen in the live mug UIDs). None = Gelato has
# no such colour (flagged unfulfillable, never silently mismapped). 'navy' has no Gelato
# equivalent (they offer 'blue') - kept None so it is surfaced, not guessed into blue.
_MUG_COLOUR_TO_GELATO = {
    "white": "white", "black": "black", "red": "red", "yellow": "yellow", "pink": "pink",
    "green": "green", "forest green": "green", "royal blue": "blue", "blue": "blue",
    "navy": None, "maroon": None, "dusty rose": None, "silver": None, "grey": None, "gray": None,
}


def _parse_gelato_mug_uid(uid: str) -> dict | None:
    """Parse a real Gelato mug productUid into {size, material, colour}. Grammar (grounded
    on the live catalog): ``mug_product_msz_<size>_mmat_<material...-colour>_cl_...``. The
    colour is the LAST hyphen-token of the material segment, the MATERIAL is the rest
    (ceramic-white -> ceramic/white; heat-transfer-black -> heat-transfer/black;
    metal-enamel-white -> metal-enamel/white). Matching on material too prevents a
    same-colour collision (ceramic-black vs heat-transfer-black) from mis-mapping."""
    m = re.search(r"_msz_(.+?)_mmat_(.+?)_cl_", uid or "")
    if not m:
        return None
    size, matcol = m.group(1), m.group(2)
    material, _, colour = matcol.rpartition("-")
    return {"size": size, "material": material or matcol, "colour": colour, "uid": uid}


def _our_mug_size_token(capacity_oz: int, product_id: str) -> str | None:
    """Our mug -> the Gelato size token. Special products carry their own size token."""
    pid = (product_id or "").lower()
    if "enamel" in pid:
        return "12-oz-enamel"
    if "travel" in pid:
        return "15-oz-travel"
    if "xl" in pid or capacity_oz == 17:
        return "17-oz-tall"
    if capacity_oz == 11:
        return "11-oz"
    if capacity_oz == 15:
        return "15-oz"
    return None


# Our mug product_id -> the Gelato MATERIAL it must map to. Products whose material has NO
# Gelato equivalent (colour-interior, two-tone accent) map to a sentinel that can never
# match, so they are flagged unfulfillable rather than silently mapped to a full-colour mug.
_MUG_MATERIAL = {
    "classic_mug": "ceramic", "large_mug": "ceramic", "xl_mug": "ceramic",
    "enamel_mug": "metal-enamel", "travel_mug": "stainless-steel",
    "color_mug": "__no-gelato-colour-interior__", "accent_mug": "__no-gelato-accent__",
}


def deterministic_mug_matches(catalog: list[dict] | None = None) -> list[dict]:
    """Map every mug SKU to a real Gelato UID by ATTRIBUTE (size+colour), verified against
    the live catalog. Returns rows ``{sku, product_id, size, colour, uid, status, reason}``
    where status is 'matched' (uid present in Gelato) or 'unfulfillable' (no such variant).
    Read-only; never writes. catalog defaults to the live 'mugs' catalog (discovery-gated)."""
    cat = _fetch_catalog("mugs") if catalog is None else catalog
    parsed = [p for p in (_parse_gelato_mug_uid(c.get("uid", "")) for c in cat) if p]
    # Index by (size, MATERIAL, colour) - material-anchored so ceramic-black and
    # heat-transfer-black can't collide, and colour-interior/accent can't match ceramic.
    index = {(p["size"], p["material"], p["colour"]): p["uid"] for p in parsed}
    from quoteforge.etsy.mug_catalog import MUG_CATALOG, _variant_sku
    rows: list[dict] = []
    for prod in MUG_CATALOG:
        size_tok = _our_mug_size_token(getattr(prod, "capacity_oz", 0), prod.product_id)
        material = _MUG_MATERIAL.get(prod.product_id, "ceramic")
        for colour in (prod.colors or ["White"]):
            sku = _variant_sku(prod, prod.sizes[0] if prod.sizes else "", colour)
            g_colour = _MUG_COLOUR_TO_GELATO.get(colour.strip().lower(), "__unknown__")
            row = {"sku": sku, "product_id": prod.product_id, "name": prod.name,
                   "size": size_tok, "material": material, "colour": colour, "uid": None,
                   "status": "unfulfillable", "reason": ""}
            if material.startswith("__no-gelato"):
                row["reason"] = f"Gelato has no {prod.name} equivalent (product type not offered)"
            elif size_tok is None:
                row["reason"] = "no Gelato size token for this product"
            elif g_colour is None:
                row["reason"] = f"Gelato offers no '{colour}' (they don't make this colour)"
            elif g_colour == "__unknown__":
                row["reason"] = f"unmapped colour '{colour}' - confirm against the catalog"
            else:
                uid = index.get((size_tok, material, g_colour))
                if uid:
                    row.update(uid=uid, status="matched",
                               reason="exact size+material+colour match")
                else:
                    row["reason"] = f"Gelato has no {size_tok} {material} mug in {g_colour}"
            rows.append(row)
    return rows


def _parse_gelato_bottle_uid(uid: str) -> dict | None:
    """``bottle_product_bsz_<size>_bmat_<material...-colour>`` -> {size, material, colour}."""
    m = re.search(r"_bsz_(.+?)_bmat_(.+?)_cl_", uid or "")
    if not m:
        return None
    material, _, colour = m.group(2).rpartition("-")
    return {"size": m.group(1), "material": material or m.group(2), "colour": colour, "uid": uid}


def deterministic_bottle_matches(catalog: list[dict] | None = None) -> list[dict]:
    """Map our bottle/tumbler SKUs to real Gelato bottle UIDs by size+colour. Gelato's
    bottle catalog is tiny (stainless only), so most of our sizes/colours flag unfulfillable
    - a real reconciliation signal. Read-only; never writes."""
    cat = _fetch_catalog("bottles") if catalog is None else catalog
    idx = {(p["size"], p["colour"]): p["uid"]
           for p in (_parse_gelato_bottle_uid(c.get("uid", "")) for c in cat) if p}
    from quoteforge.etsy.branded_catalog import BRANDED_CATALOG, _variant_sku
    rows: list[dict] = []
    for prod in BRANDED_CATALOG:
        if prod.product_id not in ("bottle", "tumbler"):
            continue
        for size in prod.sizes:
            mm = re.search(r"(\d+)\s*oz", size.lower())
            g_size = f"{mm.group(1)}-oz" if mm else None
            for colour in prod.colors:
                sku = _variant_sku(prod, size, colour)
                g_col = {"white": "white", "silver": "white",
                         "black": "black"}.get(colour.strip().lower())
                uid = idx.get((g_size, g_col)) if (g_size and g_col) else None
                rows.append({"sku": sku, "product_id": prod.product_id, "size": g_size,
                             "colour": colour, "uid": uid,
                             "status": "matched" if uid else "unfulfillable",
                             "reason": "exact size+colour match" if uid
                             else f"Gelato has no {g_size or '?'} bottle in {colour}"})
    return rows


def _bag_canonical_colour(uid: str) -> str | None:
    """Colour of a CANONICAL tote UID (standard quality clc, size std-t, single-side
    full-colour print 4-0, no manufacturer variant); None for any non-canonical variant."""
    m = re.fullmatch(r"bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_(.+?)_bpr_4-0", uid or "")
    return m.group(1) if m else None


def deterministic_bag_matches(catalog: list[dict] | None = None) -> list[dict]:
    """Map our tote SKUs to real Gelato tote UIDs by colour, using the canonical single-side
    full-colour variant. Colours Gelato doesn't offer as a clean variant are flagged."""
    cat = _fetch_catalog("tote-bags") if catalog is None else catalog
    idx = {c: u for c, u in ((_bag_canonical_colour(p.get("uid", "")), p.get("uid"))
                             for p in cat) if c}
    colmap = {"natural": "natural", "white": "white", "navy": "navy", "black": "black",
              "red": "red", "sand": None, "sage": None}
    from quoteforge.etsy.branded_catalog import BRANDED_CATALOG, _variant_sku
    rows: list[dict] = []
    for prod in BRANDED_CATALOG:
        if prod.product_id != "tote":
            continue
        for colour in prod.colors:
            sku = _variant_sku(prod, prod.sizes[0] if prod.sizes else "", colour)
            key = colour.strip().lower()
            g_col = colmap.get(key, "__unknown__")
            uid = idx.get(g_col) if g_col and g_col != "__unknown__" else None
            rows.append({"sku": sku, "product_id": "tote", "colour": colour, "uid": uid,
                         "status": "matched" if uid else "unfulfillable",
                         "reason": "exact colour match (single-side full-colour tote)" if uid
                         else (f"Gelato offers no clean '{colour}' tote variant" if g_col is None
                               else f"unmapped colour '{colour}'")})
    return rows


# Our garment type -> (Gelato garment category token, Gelato catalog uid).
_APPAREL_TYPE = {
    "tshirt": ("t-shirt", "t-shirts"), "tank": ("tank-top", "tank-tops"),
    "hoodie": ("hoodie", "hoodies"), "sweatshirt": ("sweatshirt", "sweatshirts"),
    "polo": ("polo", "polos"),
    # longsleeve/raglan: Gelato catalog not yet identified -> flagged, not guessed.
}
_APPAREL_GENDER_CUT = {"m": "unisex", "w": "womens"}    # Gelato has no 'mens' -> unisex


def _parse_gelato_apparel_uid(uid: str) -> dict | None:
    """Parse ``apparel_product_gca_<cat>_gsc_<sub>_gcu_<cut>_gqa_<quality>_gsi_<size>
    _gco_<colour>_gpr_...`` -> {category, cut, quality, size, colour}."""
    m = re.search(r"_gca_(.+?)_gsc_.+?_gcu_(.+?)_gqa_(.+?)_gsi_(.+?)_gco_(.+?)_gpr_", uid or "")
    if not m:
        return None
    return {"category": m.group(1), "cut": m.group(2), "quality": m.group(3),
            "size": m.group(4), "colour": m.group(5), "uid": uid}


# Confirmed (garment type, gender) -> (category, subcategory, cut, quality). Apparel UIDs
# are CONSTRUCTED from attributes and verified to exist - the catalog is too large to page.
# Each entry's quality is the one Gelato ACTUALLY OFFERS for that cut (probed live across
# all 9 qualities): tanks exist only in prm/performance, womens hoodie only in prm, womens
# longsleeve/sweatshirt and raglan have NO clean variant, polo is embroidery-only -> those
# combos are absent here and flag unfulfillable, never guessed.
_APPAREL_BUILD = {
    ("tshirt", "m"): ("t-shirt", "crewneck", "unisex", "classic"),
    ("tshirt", "w"): ("t-shirt", "crewneck", "womens", "classic"),
    ("sweatshirt", "m"): ("sweatshirt", "crewneck", "unisex", "classic"),
    ("longsleeve", "m"): ("t-shirt", "longsleeve-crew", "unisex", "classic"),
    ("tank", "m"): ("t-shirt", "tank-top", "unisex", "prm"),
    ("tank", "w"): ("t-shirt", "tank-top", "womens", "performance"),
    ("hoodie", "m"): ("hoodie", "pullover", "unisex", "classic"),
    ("hoodie", "w"): ("hoodie", "pullover", "womens", "prm"),
}
_APPAREL_PRINT = "0-4"                # single-side full-colour front print


def _apparel_uid(gca: str, gsc: str, cut: str, quality: str, size: str, colour: str) -> str:
    """Construct the deterministic Gelato apparel productUid from its attributes."""
    return (f"apparel_product_gca_{gca}_gsc_{gsc}_gcu_{cut}_gqa_{quality}"
            f"_gsi_{size}_gco_{colour}_gpr_{_APPAREL_PRINT}")


def _apparel_uid_exists(uid: str) -> bool:
    """True iff the constructed apparel UID is a real Gelato product (GET 200). Read-only;
    gated on discovery + never raises."""
    if not _discovery():
        return False
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        r = requests.get(f"{_PRODUCT_API}/products/{uid}",
                         headers={"X-API-KEY": GELATO_API_KEY}, timeout=15)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def deterministic_apparel_matches(quality: str | None = None,
                                  verifier=None) -> list[dict]:
    """Map every apparel SKU to a real Gelato UID by CONSTRUCTING the deterministic
    productUid (category+subcategory+cut+quality+size+colour) and VERIFYING it exists.
    Each (garment type, gender) uses the quality Gelato actually offers for that cut
    (_APPAREL_BUILD, probed live); ``quality`` overrides it when given. Combos with no
    clean Gelato variant (raglan, polo, womens longsleeve/sweatshirt) and non-existent
    size/colour combos are flagged unfulfillable, never guessed. ``verifier(uid)->bool``
    is injectable for hermetic tests (default: live GET)."""
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
    verify = verifier if verifier is not None else _apparel_uid_exists
    seen: dict = {}                 # uid -> exists (cache: one check per unique uid)
    rows: list[dict] = []
    for g in APPAREL_CATALOG:
        gm = re.match(r"^([mw])_([a-z]+?)(?:_(value|premium))?$", g.garment_id)
        gender = gm.group(1) if gm else ""
        gtype = gm.group(2) if gm else ""
        build = _APPAREL_BUILD.get((gtype, gender))
        for size in (g.sizes or []):
            for colour in (g.colors or []):
                sku = apparel_sku_for(g.garment_id, size, colour)
                g_col = colour.strip().lower().replace(" ", "-")
                g_size = size.strip().lower()
                q = quality or (build[3] if build else "")
                row = {"sku": sku, "garment_id": g.garment_id, "size": g_size,
                       "colour": colour, "quality": q, "uid": None,
                       "status": "unfulfillable", "reason": ""}
                if not build:
                    row["reason"] = (f"no clean Gelato variant for '{gender}_{gtype}' "
                                     "(cut/quality not offered)")
                else:
                    gca, gsc, cut, _dq = build
                    uid = _apparel_uid(gca, gsc, cut, q, g_size, g_col)
                    if uid not in seen:
                        seen[uid] = verify(uid)
                    if seen[uid]:
                        row.update(uid=uid, status="matched",
                                   reason="constructed + verified exists")
                    else:
                        row["reason"] = f"no Gelato {gca}/{gsc} {cut}/{q}/{g_size}/{g_col}"
                rows.append(row)
    return rows


# Deterministic mappers by category name -> (matcher, registry family).
_DETERMINISTIC = {
    "mug": (lambda cat=None: deterministic_mug_matches(catalog=cat), "mug"),
    "bottle": (lambda cat=None: deterministic_bottle_matches(catalog=cat), "branded"),
    "tote": (lambda cat=None: deterministic_bag_matches(catalog=cat), "branded"),
    "apparel": (lambda cat=None: deterministic_apparel_matches(), "apparel"),
}


def _apply_matches(rows: list[dict], family: str, *, approve: bool) -> dict:
    """Write the 'matched' rows to the registry (approve -> owner-verified via
    map_real_gelato_uid; else DRAFT). 'unfulfillable' rows are returned, never mapped."""
    from quoteforge.automation.gelato_readiness import map_real_gelato_uid, draft_uid
    written, errors = 0, []
    for r in rows:
        if r["status"] != "matched":
            continue
        try:
            if approve:
                map_real_gelato_uid(family, r["sku"], r["uid"], source="deterministic")
            else:
                draft_uid(family, r["sku"], r["uid"], score=1.0,
                          reason="deterministic attribute match", source="deterministic")
            written += 1
        except Exception as exc:  # noqa: BLE001 - a rejected write is reported, not fatal
            errors.append({"sku": r["sku"], "error": str(exc)})
    return {"matched": sum(1 for r in rows if r["status"] == "matched"),
            "unfulfillable": [r for r in rows if r["status"] == "unfulfillable"],
            "written": written, "approved": bool(approve), "errors": errors}


def apply_deterministic_matches(category: str, *, approve: bool = False,
                                catalog: list[dict] | None = None) -> dict:
    """Map a category's deterministic matches (category in {mug, bottle, tote})."""
    matcher, family = _DETERMINISTIC[category]
    return _apply_matches(matcher(catalog), family, approve=approve)


def apply_deterministic_mug_matches(*, approve: bool = False,
                                    catalog: list[dict] | None = None) -> dict:
    """Back-compat shim: map the deterministic MUG matches."""
    return _apply_matches(deterministic_mug_matches(catalog=catalog), "mug", approve=approve)
