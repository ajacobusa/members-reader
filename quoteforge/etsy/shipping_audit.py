"""Shipping-cost variance + profit-by-destination audit.

Print-on-demand shipping is destination-dependent. If the ACTUAL shipping a
vendor charges exceeds what was modeled (or what the buyer paid), margin leaks
silently - worst on far destinations and heavy/fragile materials. This module:

  - models expected shipping by destination zone x material,
  - flags orders whose actual shipping exceeds the model by more than
    SHIPPING_VARIANCE_ALERT_PCT (default 10%) or exceeds what was collected,
  - aggregates profit by country (and US state) so unprofitable lanes surface.

The zone bases + material multipliers are sensible defaults the owner can tune;
the point is a tripwire, not a carrier-exact quote.
"""
from __future__ import annotations

# Base modeled shipping (USD) by destination zone.
ZONE_BASE = {
    "domestic": 5.99,    # US
    "north_america": 9.99,    # CA, MX
    "europe": 12.99,
    "oceania_asia": 14.99,    # AU, NZ, JP, ...
    "rest": 16.99,
}

# Which countries fall in which zone (ISO-ish, upper-cased).
_ZONE_OF = {"US": "domestic", "USA": "domestic",
            "CA": "north_america", "MX": "north_america", "CANADA": "north_america",
            "GB": "europe", "UK": "europe", "DE": "europe", "FR": "europe",
            "IE": "europe", "IT": "europe", "ES": "europe", "NL": "europe",
            "AU": "oceania_asia", "NZ": "oceania_asia", "JP": "oceania_asia",
            "SG": "oceania_asia"}

# Heavier / more protective packaging => higher shipping by material/product.
# Mugs are heavy & fragile; calendars are bulkier than a flat poster.
MATERIAL_SHIP_MULT = {"poster": 1.0, "framed": 1.8, "canvas": 1.5,
                      "acrylic": 1.7, "metal": 1.7, "mug": 1.6, "calendar": 1.2}


def zone_for(country: str) -> str:
    """The shipping zone for a destination country (defaults to 'rest')."""
    return _ZONE_OF.get((country or "").strip().upper(), "rest")


def modeled_shipping(country: str, material: str) -> float:
    """Expected shipping (USD) for a destination + material/product label.

    The order's `material` is often a free-text format ("Classic Ceramic Mug (11oz)
    - White", "Wall Calendar - White"), so match the product/material class anywhere
    in the label - otherwise mugs/calendars fall back to flat-poster shipping and
    the variance tripwire never fires on their heavier real cost."""
    base = ZONE_BASE.get(zone_for(country), ZONE_BASE["rest"])
    m = (material or "poster").lower()
    mult = next((v for k, v in MATERIAL_SHIP_MULT.items() if k in m), 1.0)
    return round(base * mult, 2)


def shipping_variance(order: dict) -> dict:
    """Per-order shipping comparison: modeled vs actual vs collected.

    `leaking` is True when actual shipping exceeds the model by more than
    SHIPPING_VARIANCE_ALERT_PCT, or exceeds what the buyer was charged.
    """
    from quoteforge.config import SHIPPING_VARIANCE_ALERT_PCT
    modeled = modeled_shipping(order.get("country"), order.get("material"))
    actual = float(order.get("shipping_cost") or 0.0)
    collected = float(order.get("shipping_collected") or 0.0)
    over_model_pct = round((actual - modeled) / modeled * 100, 1) if modeled else 0.0
    leaks_model = actual > 0 and over_model_pct > SHIPPING_VARIANCE_ALERT_PCT
    leaks_collected = actual > 0 and collected > 0 and actual > collected
    return {
        "order_id": order.get("order_id", ""),
        "country": order.get("country") or "?",
        "material": order.get("material") or "?",
        "modeled": modeled,
        "actual": round(actual, 2),
        "collected": round(collected, 2),
        "over_model_pct": over_model_pct,
        "leaking": bool(leaks_model or leaks_collected),
    }


def audit_shipping(orders: list[dict]) -> dict:
    """Audit every order that has a recorded actual shipping cost. Returns the
    offenders (leaking margin) plus totals."""
    rows = [shipping_variance(o) for o in orders
            if (o.get("shipping_cost") or 0)]
    offenders = sorted((r for r in rows if r["leaking"]),
                       key=lambda r: r["over_model_pct"], reverse=True)
    total_leak = round(sum(max(0.0, r["actual"] - max(r["modeled"], r["collected"]))
                           for r in offenders), 2)
    return {
        "checked": len(rows),
        "offenders": offenders,
        "leak_count": len(offenders),
        "est_leak_usd": total_leak,
    }


def profit_by_destination(orders: list[dict]) -> list[dict]:
    """Revenue / cost / net / margin aggregated by destination country
    (sorted by revenue), so low-margin lanes are visible."""
    from quoteforge.etsy.profit_calculator import operating_order_profit
    agg: dict = {}
    for o in orders:
        if not (o.get("sale_price") or 0):
            continue
        c = (o.get("country") or "?").upper()
        p = operating_order_profit(float(o["sale_price"]),
                                   float(o.get("gelato_cost") or 0))
        ship = float(o.get("shipping_cost") or 0) - float(o.get("shipping_collected") or 0)
        net = round(p["net_profit"] - max(0.0, ship), 2)
        row = agg.setdefault(c, {"country": c, "orders": 0, "revenue": 0.0,
                                 "net": 0.0})
        row["orders"] += 1
        row["revenue"] = round(row["revenue"] + float(o["sale_price"]), 2)
        row["net"] = round(row["net"] + net, 2)
    for r in agg.values():
        r["margin_pct"] = round(r["net"] / r["revenue"] * 100, 1) if r["revenue"] else 0.0
    return sorted(agg.values(), key=lambda r: r["revenue"], reverse=True)


def format_shipping_audit_text(orders: list[dict]) -> str:
    """Printable shipping-variance + profit-by-destination report."""
    a = audit_shipping(orders)
    lines = ["=" * 56, "SHIPPING VARIANCE & PROFIT BY DESTINATION", "=" * 56,
             f"Orders with shipping data: {a['checked']}",
             f"Leaking margin: {a['leak_count']}  (est. ${a['est_leak_usd']:.2f})"]
    for o in a["offenders"][:10]:
        lines.append(f"  ! {o['order_id']:14} {o['country']:3} {o['material']:7} "
                     f"model ${o['modeled']:.2f} vs actual ${o['actual']:.2f} "
                     f"(+{o['over_model_pct']:.0f}%)")
    lines.append("\nPROFIT BY DESTINATION:")
    for r in profit_by_destination(orders)[:12]:
        lines.append(f"  {r['country']:3}  {r['orders']:>3} orders  "
                     f"${r['revenue']:>8.2f} rev  ${r['net']:>8.2f} net  "
                     f"{r['margin_pct']:>5.1f}%")
    lines.append("=" * 56)
    return "\n".join(lines)
