"""Custom Branded Products family (Gelato-fulfilled).

A self-contained parallel module modeled on apparel_catalog.py. Branded merch
differs from apparel only in shape:
  * one product line per item (no gender x tier explosion); each item is one
    listing with its own print bound (branded_dimensions_for).
  * variants are (size/variant x colour); flat products are size "One Size".
Costs are seeded (modeled) and overridden live by the Gelato sync; pricing always
re-derives from current cost to hold the 60% net-margin floor. Seed SKUs ship as
GEL-* placeholders mapped to real Gelato UIDs before go-live (verify_branded_mappings).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BRANDED_DIMS: tuple[int, int] = (3000, 3000)


@dataclass
class BrandedProduct:
    """One sellable branded product line with its sizes, colours, print geometry,
    seed cost and recommended Gelato blank."""
    product_id: str
    name: str
    type_name: str
    category: str
    sizes: list[str]
    colors: list[str]
    base_cost: float
    sku_prefix: str
    brand: str = ""
    tier: str = "Classic"
    width_px: int = DEFAULT_BRANDED_DIMS[0]
    height_px: int = DEFAULT_BRANDED_DIMS[1]
    placement: str = "front"


_BRANDED_TYPES = [
    ("tote", "Organic Cotton Tote Bag", "Tote Bag", "Bags",
     ["One Size"], ["Natural", "White", "Sand", "Sage", "Navy", "Black"],
     7.0, "Gelato Organic Tote", "Value", 3000, 3600),
    ("bottle", "Insulated Stainless Water Bottle", "Water Bottle", "Drinkware",
     ["20oz"], ["White", "Silver", "Black", "Navy", "Red"],
     12.0, "Gelato Steel Bottle", "Premium", 3600, 2400),
    ("tumbler", "Insulated Stainless Tumbler", "Tumbler", "Drinkware",
     ["20oz", "30oz"], ["White", "Silver", "Black", "Navy", "Forest Green"],
     14.0, "Gelato Steel Tumbler", "Premium", 3600, 2200),
    ("mousepad", "Rectangular Mouse Pad", "Mouse Pad", "Desk",
     ["9x7", "12x10"], ["White"], 6.0, "Gelato Mouse Pad", "Value", 2700, 2100),
    ("notebook", "Softcover Notebook", "Notebook", "Stationery",
     ["A5"], ["White", "Cream", "Black", "Navy"], 5.0, "Gelato Softcover", "Value", 1740, 2490),
    ("journal", "Hardcover Journal", "Journal", "Stationery",
     ["A5"], ["Black", "Navy", "Maroon", "Forest Green", "Sand"],
     9.0, "Gelato Hardcover", "Premium", 1740, 2490),
    ("sticker", "Die-Cut Vinyl Sticker", "Sticker", "Stickers",
     ["2x2", "3x3", "4x4"], ["White"], 2.0, "Gelato Vinyl Sticker", "Value", 1200, 1200),
    ("phonecase", "Tough Phone Case", "Phone Case", "Tech",
     ["iPhone", "Samsung"], ["White", "Black"], 8.0, "Gelato Tough Case", "Classic", 1800, 3600),
    ("keychain", "Metal Keychain", "Keychain", "Accessories",
     ["Rectangle", "Circle"], ["Silver"], 4.0, "Gelato Metal Keychain", "Value", 600, 600),
]


def _build_catalog() -> list[BrandedProduct]:
    out: list[BrandedProduct] = []
    for pid, name, type_name, cat, sizes, colors, cost, brand, tier, w, h in _BRANDED_TYPES:
        out.append(BrandedProduct(
            product_id=pid, name=name, type_name=type_name, category=cat,
            sizes=list(sizes), colors=list(colors), base_cost=cost,
            sku_prefix=f"GEL-{pid.upper()}", brand=brand, tier=tier,
            width_px=w, height_px=h))
    return out


BRANDED_CATALOG: list[BrandedProduct] = _build_catalog()


@dataclass
class BrandedVariant:
    product_id: str
    name: str
    size: str
    color: str
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    placement: str = "front"


def get_product(product_id: str) -> BrandedProduct | None:
    key = (product_id or "").strip().lower()
    return next((p for p in BRANDED_CATALOG if p.product_id == key), None)


def branded_dimensions_for(product_id: str) -> tuple[int, int]:
    p = get_product(product_id)
    return (p.width_px, p.height_px) if p else DEFAULT_BRANDED_DIMS


def _variant_sku(p: BrandedProduct, size: str, color: str) -> str:
    part = lambda s: s.upper().replace(" ", "-")
    return f"{p.sku_prefix}-{part(size)}-{part(color)}"


def _variant_cost(p: BrandedProduct, sku: str) -> float | None:
    from quoteforge.etsy.catalog_state import sku_override
    ov = sku_override(sku)
    if ov and ov.get("available") is False:
        return None
    if ov and ov.get("cost") is not None:
        return round(ov["cost"], 2)
    return round(p.base_cost, 2)


def _list_floor(floor_pct: float | None) -> float:
    from quoteforge.config import LIST_MARGIN_PCT, TARGET_MARGIN_PCT
    if floor_pct is not None:
        return max(floor_pct, TARGET_MARGIN_PCT)
    return max(LIST_MARGIN_PCT, TARGET_MARGIN_PCT)


def build_branded_variations(floor_pct: float | None = None) -> list[BrandedVariant]:
    from quoteforge.etsy.variations import min_price_for_margin, net_margin_pct
    floor = _list_floor(floor_pct)
    out: list[BrandedVariant] = []
    for p in BRANDED_CATALOG:
        for size in p.sizes:
            for color in p.colors:
                sku = _variant_sku(p, size, color)
                cost = _variant_cost(p, sku)
                if cost is None:
                    continue
                price = min_price_for_margin(cost, floor)
                out.append(BrandedVariant(
                    product_id=p.product_id, name=p.name, size=size, color=color,
                    gelato_sku=sku, gelato_cost=cost, price=price,
                    margin_pct=net_margin_pct(price, cost), placement=p.placement))
    return out


def branded_skus() -> list[str]:
    return sorted({_variant_sku(p, s, c)
                   for p in BRANDED_CATALOG for s in p.sizes for c in p.colors})
