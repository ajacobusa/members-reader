"""Dynamic colour/size -> Gelato variant UID resolution.

Instead of pre-mapping every (garment, colour, size) SKU to a Gelato product UID
(thousands of them), the owner maps ONE Gelato "product family" per
(garment_type, tier) - about 21 entries. At order time we resolve the exact
variant UID for the chosen colour + size from that family via Gelato's catalog
API, and cache the result.

Resolution order for a SKU:
  1. A statically-mapped REAL UID in GELATO_UID_MAP wins (the old full-map path
     keeps working, and lets an owner pin a specific variant).
  2. Else, if the SKU's (garment_type, tier) family is mapped AND the API is live,
     resolve the variant UID from Gelato by attribute search, and cache it.
  3. Else None -> the caller routes to manual review (placeholder guard).

Key-gated + TEST_MODE-safe: with no key, in TEST_MODE, or with no family mapped,
the dynamic path is a no-op and returns None, so nothing changes until the owner
is genuinely live. The single un-verifiable seam is the exact Gelato attribute
search request/response shape in `_gelato_search_variant` - it is defensive
(never raises, returns None on anything unexpected) and is the one thing to
confirm against a live Gelato account.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_PRODUCT_API = "https://product.gelatoapis.com/v3"


def _family_map() -> dict:
    """(garment_type:tier) -> Gelato product-family identifier. From
    GELATO_PRODUCT_FAMILY_MAP (inline JSON env) AND/OR GELATO_PRODUCT_FAMILY_FILE
    (path to a JSON file, merged over the env). ~21 entries replace thousands of
    per-variant SKU mappings."""
    out: dict = {}
    raw = os.getenv("GELATO_PRODUCT_FAMILY_MAP", "").strip()
    if raw:
        try:
            out.update(json.loads(raw))
        except Exception as exc:  # noqa: BLE001 - malformed env JSON ignored
            logger.debug("GELATO_PRODUCT_FAMILY_MAP parse failed: %s", exc)
    path = os.getenv("GELATO_PRODUCT_FAMILY_FILE", "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                out.update(json.load(fh))
        except Exception as exc:  # noqa: BLE001 - unreadable family file ignored
            logger.debug("GELATO_PRODUCT_FAMILY_FILE load failed: %s", exc)
    return out


def family_key(garment_id: str) -> str | None:
    """The family-map key for a product id, across EVERY department. Apparel
    garments use '<garment_type>:<tier>' (e.g. 'tshirt:Classic'); the branded /
    mug / calendar departments each use '<dept>:<product_id>' (one family per
    product line). Returns None for an unknown id. The family map gates which
    products are considered mapped; note that DYNAMIC per-variant resolution
    (resolve_variant_uid's API search) is apparel-only - mug / branded / calendar
    still require a static per-SKU UID, because their Gelato attributes differ
    from apparel's GarmentColor/GarmentSize."""
    import importlib
    pid = (garment_id or "").strip().lower()
    if not pid:
        return None
    from quoteforge.etsy.apparel_catalog import get_garment
    g = get_garment(pid)
    if g:
        return f"{g.garment_type}:{getattr(g, 'tier', 'Classic')}"
    for dept, mod_name, getter in (("branded", "branded_catalog", "get_product"),
                                   ("mug", "mug_catalog", "get_mug"),
                                   ("calendar", "calendar_catalog", "get_calendar")):
        try:
            mod = importlib.import_module(f"quoteforge.etsy.{mod_name}")
            p = getattr(mod, getter)(pid)
            if p:
                return f"{dept}:{p.product_id}"
        except Exception:  # noqa: BLE001 - a missing dept module never breaks resolution
            continue
    return None


def _family_value(garment_id: str) -> str | None:
    """The mapped Gelato family identifier for a garment, or None if unmapped /
    still a placeholder (GEL-*)."""
    key = family_key(garment_id)
    if not key:
        return None
    val = _family_map().get(key)
    if not val or str(val).upper().startswith("GEL-"):
        return None
    return val


def family_covered(garment_id: str) -> bool:
    """True when a FAMILY mapping alone makes every colour/size resolvable at order
    time. That is APPAREL-ONLY: resolve_variant_uid's dynamic search uses apparel
    attributes (GarmentColor/GarmentSize), so mug / branded / calendar products are
    NOT covered by a family mapping - they need a static per-SKU UID. Returning
    False for them keeps the go-live readiness report HONEST (it previously showed
    them READY while every such order silently routed to manual)."""
    from quoteforge.etsy.apparel_catalog import get_garment
    if not get_garment((garment_id or "").strip().lower()):
        return False
    return _family_value(garment_id) is not None


# ── SKU -> (garment_id, colour, size) reverse index ──────────────

_SKU_INDEX: dict | None = None


def _sku_index() -> dict:
    """Lazy {variant_sku: (garment_id, colour, size)} map, built once from the
    catalogue, so a SKU can be resolved without re-parsing its string."""
    global _SKU_INDEX
    if _SKU_INDEX is None:
        from quoteforge.etsy.apparel_catalog import build_apparel_variations
        idx: dict = {}
        try:
            for v in build_apparel_variations():
                idx[v.gelato_sku] = (v.garment_id, v.color, v.size)
        except Exception:  # noqa: BLE001
            idx = {}
        _SKU_INDEX = idx
    return _SKU_INDEX


# ── Resolved-UID cache (so we don't re-hit the API every order) ──

def _cache_path():
    """Path to the resolved-UID JSON cache (GELATO_VARIANT_CACHE or OUTPUT_DIR)."""
    from pathlib import Path
    p = os.getenv("GELATO_VARIANT_CACHE", "").strip()
    if p:
        return Path(p)
    from quoteforge.config import OUTPUT_DIR
    return Path(OUTPUT_DIR) / "gelato_variant_uids.json"


def _load_cache() -> dict:
    """Load the resolved SKU->UID cache (empty dict if missing/unreadable)."""
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    """Persist the resolved SKU->UID cache; best-effort, never raises."""
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - cache is best-effort
        logger.debug("variant cache write failed: %s", exc)


def _attr(value: str) -> str:
    """Normalise a colour/size name to a Gelato attribute value (best-effort)."""
    return (value or "").strip().lower().replace(" ", "-").replace("/", "-")


def _gelato_search_variant(family: str, color: str, size: str) -> str | None:
    """Resolve a variant productUid from a Gelato product family + colour + size.

    DEFENSIVE provider seam: posts an attribute search to Gelato and extracts the
    first matching productUid. Never raises; returns None on anything unexpected.
    Confirm the exact request/response shape against a live Gelato account.
    """
    import requests
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    try:
        resp = requests.post(
            f"{_PRODUCT_API}/products:search",
            headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
            json={"catalogProductUid": family,
                  "attributeFilters": {"GarmentColor": [_attr(color)],
                                       "GarmentSize": [_attr(size)]}},
            timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.json()
        hits = data.get("products") or data.get("hits") or data.get("data") or []
        if isinstance(hits, list) and hits:
            first = hits[0]
            if isinstance(first, dict):
                for k in ("productUid", "uid", "id"):
                    v = first.get(k)
                    if isinstance(v, str) and v:
                        return v
            elif isinstance(first, str):
                return first
    except Exception:  # noqa: BLE001 — network/parse blip -> manual review
        return None
    return None


def resolve_variant_uid(sku: str | None, garment_id: str | None = None,
                        color: str | None = None, size: str | None = None) -> str | None:
    """Real Gelato variant UID for a SKU, or None (-> manual review).

    Static map wins; else dynamic family resolution (live only); else None.
    """
    if not sku:
        return None
    # 1. Statically-mapped real UID wins - and CLEARS any stale dynamically-cached UID
    #    for this SKU (#uidremap), so a corrected static entry can never be undermined by
    #    an old dynamic value resurfacing if that static entry is later edited/removed.
    from quoteforge.automation.gelato_sync import _uid_map
    static = _uid_map().get(sku)
    if static and not str(static).upper().startswith("GEL-"):
        try:
            _c = _load_cache()
            if _c.pop(sku, None) is not None:
                _save_cache(_c)
        except Exception as exc:  # noqa: BLE001 - cache cleanup is best-effort
            logger.debug("variant cache cleanup skipped for %s: %s", sku, exc)
        return static
    # 2. Dynamic family resolution (no-op unless live + family mapped).
    from quoteforge.config import TEST_MODE
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    if TEST_MODE or not GELATO_API_KEY:
        return None
    if not (garment_id and color and size):
        garment_id, color, size = _sku_index().get(sku, (None, None, None))
    if not garment_id:
        return None
    family = _family_value(garment_id)
    if not family:
        return None
    # The dynamic variant search posts apparel attribute names
    # (GarmentColor/GarmentSize), which only exist on apparel products. A mug,
    # bottle, tote or calendar in Gelato's catalogue uses different attributes, so
    # the search would never match - it must resolve via a static per-SKU UID
    # (handled above). Returning None here routes those to MANUAL rather than
    # firing a search that silently can't match (and falsely implying the family
    # map auto-resolves them).
    from quoteforge.etsy.apparel_catalog import get_garment
    if not get_garment((garment_id or "").strip().lower()):
        return None
    cache = _load_cache()
    if sku in cache:
        return cache[sku] or None
    uid = _gelato_search_variant(family, color or "", size or "")
    cache[sku] = uid or ""
    _save_cache(cache)
    return uid
