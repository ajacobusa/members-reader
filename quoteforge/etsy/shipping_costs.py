"""Per-product shipping COST model — the high-end US estimates + safety margin used so
shipping (baked into the price, or charged) NEVER loses money, and the baseline the
shipping-rate monitor agent re-checks against Gelato.

Gelato's real shipping cost varies by product, size, destination and which hub fills
the order, and Gelato updates rates regularly — so there is no single flat number. We
deliberately take the HIGH end of the range per product TYPE, add SHIPPING_MARGIN_PCT,
and add each extra item (multi-item orders) at ADDITIONAL_ITEM_SHIP_FACTOR. The only
exact number is the Gelato dashboard; the monitor flags when our table looks stale or
could be under-covering. Customer-safe: pure numbers, never a supplier/marketplace name.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# High-end US-domestic shipping cost (USD) for the FIRST item, keyed by a product-TYPE
# keyword found in the material/format string. Owner-overridable via
# SHIPPING_COST_TABLE_JSON. Values are the HIGH end of the Gelato dashboard range.
_BASE_TABLE = {
    "framed": 25.0, "frame": 25.0, "canvas": 25.0,        # heaviest
    "poster": 15.0, "print": 15.0, "art": 15.0,
    "calendar": 15.0, "card": 15.0, "stationery": 15.0,
    "mug": 14.0,
    "apparel": 14.0, "tshirt": 14.0, "t-shirt": 14.0, "shirt": 14.0,
    "hoodie": 14.0, "tee": 14.0, "sweatshirt": 14.0, "branded": 14.0,
}
# Unknown product -> assume the high end so we never quietly under-charge shipping.
_DEFAULT_HIGH = 25.0


def shipping_table() -> dict:
    """The per-type cost table with any SHIPPING_COST_TABLE_JSON override merged in."""
    from quoteforge.config import SHIPPING_COST_TABLE_JSON
    table = dict(_BASE_TABLE)
    if SHIPPING_COST_TABLE_JSON:
        try:
            table.update({str(k).lower(): float(v)
                          for k, v in json.loads(SHIPPING_COST_TABLE_JSON).items()})
        except Exception as exc:  # noqa: BLE001 - a bad override falls back to the table
            logger.warning("SHIPPING_COST_TABLE_JSON ignored (bad JSON): %s", exc)
    return table


def first_item_cost(product_type: str) -> float:
    """High-end shipping cost for ONE item of `product_type`. Matches the LONGEST table
    keyword present (so 'framed poster' -> framed, not poster); unknown -> the high
    default (never under-charge)."""
    t = (product_type or "").lower()
    best = None
    for kw, cost in shipping_table().items():
        # whole-word match so 'framed' never matches inside 'unframed', etc.
        if re.search(r"\b" + re.escape(kw) + r"\b", t) and (best is None or len(kw) > len(best[0])):
            best = (kw, cost)
    return best[1] if best else _DEFAULT_HIGH


def shipping_cost(product_type: str, quantity: int = 1) -> float:
    """Landed shipping cost for `quantity` of `product_type`: the first item full +
    each ADDITIONAL item at ADDITIONAL_ITEM_SHIP_FACTOR, all + SHIPPING_MARGIN_PCT.
    Always the HIGH end — built so we never lose money on shipping."""
    from quoteforge.config import SHIPPING_MARGIN_PCT, ADDITIONAL_ITEM_SHIP_FACTOR
    qty = max(1, int(quantity or 1))
    base = first_item_cost(product_type)
    raw = base + base * float(ADDITIONAL_ITEM_SHIP_FACTOR) * (qty - 1)
    return round(raw * (1.0 + float(SHIPPING_MARGIN_PCT) / 100.0), 2)


def express_upcharge(product_type: str, quantity: int = 1) -> float:
    """The EXTRA the buyer pays for express vs standard for this order:
    standard landed cost x (EXPRESS_SHIP_MULT - 1). Margin already in the standard."""
    from quoteforge.config import EXPRESS_SHIP_MULT
    return round(shipping_cost(product_type, quantity) * (float(EXPRESS_SHIP_MULT) - 1.0), 2)


def landed_price(base_price: float, product_type: str, quantity: int = 1) -> float:
    """Shipping-inclusive ('landed') price = item price + the high-end shipping cost,
    for the free-shipping strategy (price includes shipping, shipping shown free).
    The shipping component already carries the safety margin."""
    return round(float(base_price) + shipping_cost(product_type, quantity), 2)


def cost_summary() -> list:
    """Per-type {type, first_item, with_margin} rows for the monitor/report."""
    from quoteforge.config import SHIPPING_MARGIN_PCT
    seen, rows = set(), []
    for kw, base in shipping_table().items():
        if base in seen:
            continue
        seen.add(base)
        rows.append({"type": kw, "first_item": round(base, 2),
                     "charged_w_margin": round(base * (1 + SHIPPING_MARGIN_PCT / 100.0), 2)})
    return sorted(rows, key=lambda r: -r["first_item"])
