"""Single registry of non-wall-art product FAMILIES.

Before this module the per-family wiring was hand-duplicated across the two ingest
seams (webhook_server._build_order_data + pipeline_orchestrator.run_full_pipeline) and
the render-size if/elif - so adding a family meant editing 4+ places, and a miss
degraded silently (a wrong-sized print). Now a new family is ONE entry here:

    Family("tote", enrich_tote_order, lambda od, sk: tote_dimensions_for(od["product_id"]),
           lambda od, sk: sk)

Wall art is intentionally NOT a family - it is the default path (no enrich step); its
sizes come from gelato_catalog.dimensions_for. WALLART_TYPES lists the product_type
values that legitimately use that default, so an UNKNOWN type fails loudly instead of
silently rendering at the poster size.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Family:
    """One non-wall-art product family and everything the pipeline needs for it."""
    product_type: str
    enrich: Callable            # enrich(order_data: dict) -> dict of fields to merge
    render_size: Callable       # (order_data, size_key) -> (width_px, height_px)
    photo_size: Callable        # (order_data, size_key) -> physical size str for the DPI gate


def _build() -> list:
    """Construct the registry (lazy imports avoid a circular dependency at import)."""
    from quoteforge.etsy.apparel_catalog import (enrich_apparel_order,
                                                 apparel_dimensions_for)
    from quoteforge.etsy.branded_catalog import (enrich_branded_order,
                                                 branded_dimensions_for)
    from quoteforge.etsy.mug_catalog import enrich_mug_order, mug_dimensions_for
    from quoteforge.etsy.calendar_catalog import (enrich_calendar_order,
                                                  calendar_dimensions_for)
    return [
        Family("apparel", enrich_apparel_order,
               lambda od, sk: apparel_dimensions_for(od.get("garment_id", "")),
               lambda od, sk: "12x16 in"),          # garment chest area for the DPI gate
        Family("mug", enrich_mug_order,
               lambda od, sk: mug_dimensions_for(od.get("product_id", "")),
               lambda od, sk: sk),
        Family("calendar", enrich_calendar_order,
               lambda od, sk: calendar_dimensions_for(od.get("product_id", "")),
               lambda od, sk: sk),
        Family("branded", enrich_branded_order,
               lambda od, sk: branded_dimensions_for(od.get("product_id", "")),
               lambda od, sk: sk),
    ]


FAMILIES = _build()
_BY_TYPE = {f.product_type: f for f in FAMILIES}

# product_type values that correctly use the wall-art poster default render size.
WALLART_TYPES = frozenset({"", "print", "poster", "canvas", "framed",
                           "metal", "acrylic", "wall_art", "wallart"})


def enrichers() -> list:
    """The enrich callables, in order - iterate this in EVERY ingest seam. Each is a
    no-op for an order that isn't its family, so running all of them is always safe."""
    return [f.enrich for f in FAMILIES]


def family_for(product_type: str):
    """The Family for a product_type, or None (wall art / unknown)."""
    return _BY_TYPE.get((product_type or "").strip().lower())
