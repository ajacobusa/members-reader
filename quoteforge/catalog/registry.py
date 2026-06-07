"""Multi-vendor product/service registry.

Designed so you can add ANY product, service, or vendor from day one without
code changes - custom items live in the DB (catalog_items). The built-in Gelato
catalog is included automatically, and new vendors (Printful, Printify, a local
framer, digital downloads, design services) just need an entry here + items.

Fulfillment types:
  api     - vendor has an API we can auto-route orders to (e.g. Gelato)
  manual  - you place the order with the vendor by hand
  digital - instant digital delivery, no physical fulfillment (cost ~0)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Vendor:
    id: str
    name: str
    fulfillment: str           # api | manual | digital
    note: str = ""


# Built-in vendors. Add a line to onboard a new supplier - nothing else needed.
VENDORS: list[Vendor] = [
    Vendor("gelato", "Gelato", "api", "Primary POD - live price/availability sync"),
    Vendor("printful", "Printful", "manual", "Add API key to automate later"),
    Vendor("printify", "Printify", "manual", "Alternate POD vendor"),
    Vendor("local", "Local supplier / framer", "manual", "Hand-fulfilled items"),
    Vendor("digital", "Digital download", "digital", "Instant delivery, ~$0 COGS"),
    Vendor("service", "Service", "manual", "Custom design / framing / setup fees"),
]


# Sensible default net-margin floors by vendor (services/digital can be higher).
DEFAULT_VENDOR_FLOORS = {"digital": 90.0, "service": 80.0}


def floor_for_vendor(vendor: str) -> float:
    """Net-margin floor for a vendor: config override > default > global 60%."""
    from quoteforge.config import TARGET_MARGIN_PCT, VENDOR_MARGIN_FLOORS_JSON
    import json
    floors = dict(DEFAULT_VENDOR_FLOORS)
    if VENDOR_MARGIN_FLOORS_JSON:
        try:
            floors.update({k: float(v) for k, v in
                           json.loads(VENDOR_MARGIN_FLOORS_JSON).items()})
        except Exception:  # noqa: BLE001
            pass
    return max(float(floors.get(vendor, TARGET_MARGIN_PCT)), TARGET_MARGIN_PCT)


def get_vendor(vendor_id: str) -> Vendor | None:
    return next((v for v in VENDORS if v.id == vendor_id), None)


def vendor_ids() -> set[str]:
    return {v.id for v in VENDORS}


def list_products(include_builtin: bool = True) -> list[dict]:
    """All sellable items: custom catalog_items (any vendor) + the built-in
    Gelato catalog. Uniform shape for pricing/ledger/UX."""
    from quoteforge.db.database import init_db, get_catalog_items
    init_db()
    items: list[dict] = []
    if include_builtin:
        try:
            from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
            for p in GELATO_CATALOG:
                items.append({
                    "vendor": "gelato", "sku": p.gelato_sku, "name": p.name,
                    "category": p.category, "item_type": "print",
                    "cost": p.gelato_cost_usd, "price": p.suggested_price.get("mid", 0),
                    "source": "builtin",
                })
        except Exception:  # noqa: BLE001
            pass
    for it in get_catalog_items():
        items.append({
            "vendor": it["vendor"], "sku": it.get("sku", ""), "name": it["name"],
            "category": it.get("category", ""), "item_type": it.get("item_type", "print"),
            "cost": it.get("cost", 0), "price": it.get("price", 0), "source": "custom",
        })
    return items


def add_product(name: str, vendor: str = "gelato", sku: str = "",
                category: str = "", item_type: str = "print",
                cost: float = 0.0, price: float = 0.0) -> dict:
    """Add a product/service from any vendor. Validates the vendor id."""
    if vendor not in vendor_ids():
        raise ValueError(f"Unknown vendor '{vendor}'. Known: {sorted(vendor_ids())}. "
                         "Add it to VENDORS in catalog/registry.py first.")
    # Auto-price to clear this vendor's margin floor if no price was given.
    if not price:
        price = suggested_price(cost, vendor)
    from quoteforge.db.database import add_catalog_item
    item_id = add_catalog_item(name, vendor, sku, category, item_type, cost, price)
    return {"id": item_id, "vendor": vendor, "name": name, "type": item_type,
            "price": price, "floor_pct": floor_for_vendor(vendor)}


def suggested_price(cost: float, vendor: str = "gelato") -> float:
    """Lowest .99 price that clears this vendor's net-margin floor."""
    from quoteforge.etsy.variations import min_price_for_margin
    return min_price_for_margin(float(cost or 0), floor_for_vendor(vendor))


def vendor_summary() -> str:
    from collections import Counter
    prods = list_products()
    by_vendor = Counter(p["vendor"] for p in prods)
    lines = ["=" * 56, "VENDORS & CATALOG", "=" * 56, "Vendors (add more in code):"]
    for v in VENDORS:
        lines.append(f"  - {v.id:9} {v.name:26} [{v.fulfillment}]  {by_vendor.get(v.id,0)} items")
    lines += ["-" * 56, f"Total sellable items: {len(prods)}",
              "Add one: admin add-product \"Name\" vendor [sku] [category] "
              "[type] [cost] [price]", "=" * 56]
    return "\n".join(lines)
