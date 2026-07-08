"""Storefront fulfillability filter (end-to-end audit gap 1 - the money-path Critical).

The storefront must only OFFER variants we can actually make: a customer who designs and
PAYS for a Sage raglan (no Gelato UID) parks at hold_validation after money moved - owner
refunds by hand, customer told nothing. The single source of truth is the drift-checked
approved-UID export ``config/gelato_uid_map.json`` (what `gelato-readiness export` writes
and invariant #60 certifies against the registry).

Semantics (deliberately conservative, per-family activation):
  * A family's filter ACTIVATES only when the export map holds >=1 real UID for that
    family's SKUs. A completely unmapped family (e.g. calendars pre-mapping) keeps its
    legacy behaviour - it is still protected downstream by the go-live gates + the
    hold_validation park; we don't gut whole sections before their mapping pass exists.
  * Within an ACTIVE family: a variant is offered only when its exact SKU resolves to a
    real (non-GEL-*) UID; a product with ZERO mapped variants is dropped entirely
    (raglan/polo/colour-interior tiles disappear, like NON_SELLABLE_BRANDED).
  * Fail-open on an unreadable map file ONLY when nothing was ever exported; a present-
    but-corrupt file fails CLOSED for active families (empty coverage -> nothing offered)
    rather than silently selling everything.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_EXPORT_FILE = os.path.join("config", "gelato_uid_map.json")


def approved_export_map() -> dict:
    """The approved-UID export map ({} when absent/unreadable). Real UIDs only."""
    try:
        if not os.path.exists(_EXPORT_FILE):
            return {}
        with open(_EXPORT_FILE, encoding="utf-8") as fh:
            raw = json.load(fh) or {}
        return {k: v for k, v in raw.items()
                if v and not str(v).upper().startswith("GEL-")}
    except Exception as exc:  # noqa: BLE001 - corrupt file: log loud, treat as empty
        logger.warning("approved uid export unreadable (%s): %s", _EXPORT_FILE, exc)
        return {}


def sku_fulfillable(sku: str, mapping: dict | None = None) -> bool:
    """True iff ``sku`` resolves to a real UID in the approved export."""
    m = approved_export_map() if mapping is None else mapping
    return bool(sku) and sku in m


@lru_cache(maxsize=1)
def _map_cache_key() -> tuple:
    """Cache seed: (mtime, size) of the export file so a re-export refreshes filters."""
    try:
        st = os.stat(_EXPORT_FILE)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def family_active(family_skus) -> bool:
    """True when the export map covers >=1 of ``family_skus`` (the filter activates)."""
    m = approved_export_map()
    return any(s in m for s in family_skus if s)


def fulfillable_apparel_variations(floor_pct: float | None = None) -> list:
    """build_apparel_variations() filtered to variants whose SKU has a real approved UID.
    When the apparel family has NO coverage at all (pre-mapping), returns the unfiltered
    list (legacy behaviour)."""
    from quoteforge.etsy.apparel_catalog import build_apparel_variations
    vs = build_apparel_variations(floor_pct)
    m = approved_export_map()
    if not any(v.gelato_sku in m for v in vs):
        return vs                                # family not mapped yet: legacy
    return [v for v in vs if v.gelato_sku in m]


def fulfillable_apparel_facets(garment) -> tuple[list, list] | None:
    """(colors, sizes) for one garment, filtered to combos with a real approved UID.
    Colours keep only those mapped for >=1 size; sizes only those mapped for >=1 colour
    (the per-colour size list is enforced exactly by the sizemap built from
    fulfillable_apparel_variations). Returns None when the garment has ZERO coverage
    (drop the tile) - or the unfiltered facets when the whole family is unmapped."""
    from quoteforge.etsy.apparel_catalog import apparel_sku_for, build_apparel_variations
    m = approved_export_map()
    fam_active = any(v.gelato_sku in m for v in build_apparel_variations())
    if not fam_active:
        return (list(garment.colors), list(garment.sizes))
    colors = [c for c in garment.colors
              if any(apparel_sku_for(garment.garment_id, s, c) in m
                     for s in garment.sizes)]
    sizes = [s for s in garment.sizes
             if any(apparel_sku_for(garment.garment_id, s, c) in m
                    for c in garment.colors)]
    if not colors or not sizes:
        return None
    return (colors, sizes)


def fulfillable_mug_variations() -> list:
    """build_mug_variations() filtered to variants with a real approved UID (family-aware:
    unfiltered when the mug family has no coverage yet)."""
    from quoteforge.etsy.mug_catalog import build_mug_variations
    vs = build_mug_variations()
    m = approved_export_map()
    if not any(v.gelato_sku in m for v in vs):
        return vs
    return [v for v in vs if v.gelato_sku in m]


def fulfillable_branded_variations() -> list:
    """build_branded_variations() filtered to variants with a real approved UID
    (family-aware: unfiltered when the branded family has no coverage yet)."""
    from quoteforge.etsy.branded_catalog import build_branded_variations
    vs = build_branded_variations()
    m = approved_export_map()
    if not any(v.gelato_sku in m for v in vs):
        return vs
    return [v for v in vs if v.gelato_sku in m]


def fulfillable_mug_facets(product) -> list | None:
    """Colours of one mug product with a real approved UID; None = zero coverage (drop
    the tile); unfiltered when the mug family has no coverage at all."""
    from quoteforge.etsy.mug_catalog import MUG_CATALOG, _variant_sku
    m = approved_export_map()
    fam = [_variant_sku(p, s, c)
           for p in MUG_CATALOG for s in (p.sizes or [""]) for c in (p.colors or [""])]
    if not any(s in m for s in fam):
        return list(product.colors)
    colors = [c for c in (product.colors or [])
              if any(_variant_sku(product, s, c) in m for s in (product.sizes or [""]))]
    return colors or None


def fulfillable_branded_facets(product) -> list | None:
    """Colours of one branded product with a real approved UID; None = zero coverage;
    unfiltered when the branded family has no coverage at all."""
    from quoteforge.etsy.branded_catalog import BRANDED_CATALOG, _variant_sku
    m = approved_export_map()
    fam = [_variant_sku(p, s, c)
           for p in BRANDED_CATALOG
           for s in (getattr(p, "sizes", None) or [""])
           for c in (getattr(p, "colors", None) or [""])]
    if not any(s in m for s in fam):
        return list(getattr(product, "colors", []) or [])
    colors = [c for c in (getattr(product, "colors", []) or [])
              if any(_variant_sku(product, s, c) in m
                     for s in (getattr(product, "sizes", None) or [""]))]
    return colors or None
