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
    returns [] without a key / in TEST_MODE / on any unexpected shape. The exact request +
    response shape is the single thing to confirm against a live Gelato account."""
    if not _live():
        return []
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        headers = {"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"}
        url = f"{_PRODUCT_API}/catalogs" + (f"/{catalog_uid}/products" if catalog_uid else "")
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning("gelato catalog fetch %s -> %s", url, resp.status_code)
            return []
        data = resp.json()
        rows = (data if isinstance(data, list)
                else data.get("products") or data.get("data") or data.get("catalogs") or [])
        out = [p for p in (_normalise_product(r) for r in rows if isinstance(r, dict)) if p]
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
    parts (type/size/colour). E.g. GEL-M-TSHIRT-M-WHITE -> {tshirt, m, white, apparel,...}."""
    return _norm_tokens(sku) | _norm_tokens(family)


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
                catalog: list[dict] | None = None) -> dict:
    """Resolve every unmapped sellable SKU against the Gelato catalog.

    apply=False (default) is a DRY RUN - reports what would be written. apply=True writes
    only matches at/above the confidence threshold to the registry (via map_real_gelato_uid,
    which still refuses a GEL-*). Everything below threshold is BLOCKED (reported, never
    written). Never raises; live-gated (empty catalog -> nothing resolved).
    """
    thr = _min_confidence() if min_confidence is None else min_confidence
    cat = _fetch_catalog() if catalog is None else catalog
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
               "sample_resolved": resolved[:5], "sample_blocked": blocked[:5]}
    logger.info("gelato-resolve: catalog=%d resolved=%d blocked=%d written=%d live=%s",
                len(cat), len(resolved), len(blocked), written, _live())
    return summary


def resolver_status() -> dict:
    """A quick read of resolver readiness: is it live, how many SKUs still need a UID."""
    items = _our_unmapped_items()
    return {"live": _live(), "unmapped_candidates": len(items),
            "threshold": _min_confidence()}
