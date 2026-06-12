"""Production Capacity Monitor - vendor fulfillment speed, delays & defect rates.

From real order timestamps it measures, per vendor:
  - production time  (order/proof-approved -> shipped)
  - shipping time    (shipped -> delivered)
  - in-flight orders past their SLA (PRODUCTION_DAYS / SHIPPING_DAYS)
  - defect rate      (reprint/defect/refunded / total)

Flags vendors breaching SLA and recommends rerouting to the best performer. All
metrics are computed from real orders; pre-launch everything is empty/zero.
"""
from __future__ import annotations
from datetime import datetime

DEFECT_STATUSES = ("reprint", "defect", "refunded", "remake")


def _parse(ts: str):
    """Parse an ISO timestamp (tolerating trailing Z); None on failure."""
    try:
        return datetime.fromisoformat((ts or "").replace("Z", ""))
    except (ValueError, TypeError):
        return None


def _hours(a: str, b: str):
    """Elapsed hours between two ISO timestamps, or None if either is invalid."""
    da, db = _parse(a), _parse(b)
    if not da or not db:
        return None
    return round((db - da).total_seconds() / 3600.0, 1)


def vendor_metrics(orders: list[dict] | None = None) -> dict:
    """Per-vendor production/shipping speed + defect rate from real orders."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    rows = get_all_orders(limit=100000) if orders is None else orders
    agg: dict[str, dict] = {}
    for o in rows:
        v = (o.get("vendor") or "gelato").strip() or "gelato"
        a = agg.setdefault(v, {"vendor": v, "orders": 0, "shipped": 0,
                               "delivered": 0, "defects": 0,
                               "_prod_hrs": [], "_ship_hrs": []})
        a["orders"] += 1
        if (o.get("status") or "").lower() in DEFECT_STATUSES:
            a["defects"] += 1
        start = o.get("proof_approved_at") or o.get("created_at")
        if o.get("shipped_at"):
            a["shipped"] += 1
            h = _hours(start, o["shipped_at"])
            if h is not None and h >= 0:
                a["_prod_hrs"].append(h)
        if o.get("delivered_at") and o.get("shipped_at"):
            a["delivered"] += 1
            h = _hours(o["shipped_at"], o["delivered_at"])
            if h is not None and h >= 0:
                a["_ship_hrs"].append(h)
    out = {}
    for v, a in agg.items():
        prod = a.pop("_prod_hrs")
        ship = a.pop("_ship_hrs")
        a["avg_production_days"] = round(sum(prod) / len(prod) / 24, 2) if prod else None
        a["avg_shipping_days"] = round(sum(ship) / len(ship) / 24, 2) if ship else None
        a["defect_rate_pct"] = round(a["defects"] / a["orders"] * 100, 1) if a["orders"] else 0.0
        out[v] = a
    return out


def overdue_orders(now: datetime | None = None,
                   orders: list[dict] | None = None) -> list[dict]:
    """In-flight orders past their production/shipping SLA."""
    from quoteforge.config import PRODUCTION_DAYS, SHIPPING_DAYS
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    now = now or datetime.now()
    rows = get_all_orders(limit=100000) if orders is None else orders
    late = []
    for o in rows:
        st = (o.get("status") or "").lower()
        if st in ("delivered", "cancelled", "refunded"):
            continue
        if not o.get("shipped_at"):       # still in production
            start = _parse(o.get("proof_approved_at") or o.get("created_at"))
            if start and (now - start).days > PRODUCTION_DAYS:
                late.append({"order_id": o.get("order_id"), "vendor": o.get("vendor"),
                             "stage": "production",
                             "days_late": (now - start).days - PRODUCTION_DAYS})
        elif not o.get("delivered_at"):   # shipped, not delivered
            start = _parse(o.get("shipped_at"))
            if start and (now - start).days > SHIPPING_DAYS:
                late.append({"order_id": o.get("order_id"), "vendor": o.get("vendor"),
                             "stage": "shipping",
                             "days_late": (now - start).days - SHIPPING_DAYS})
    return sorted(late, key=lambda x: x["days_late"], reverse=True)


def best_vendor(metrics: dict | None = None) -> str | None:
    """Vendor with the lowest production time + acceptable defect rate."""
    m = metrics if metrics is not None else vendor_metrics()
    eligible = [a for a in m.values()
                if a["avg_production_days"] is not None and a["defect_rate_pct"] < 5]
    if not eligible:
        return None
    return min(eligible, key=lambda a: a["avg_production_days"])["vendor"]


def capacity_report(now: datetime | None = None) -> dict:
    """Combine vendor metrics, overdue orders, SLA alerts and best-vendor pick."""
    m = vendor_metrics()
    late = overdue_orders(now)
    from quoteforge.config import PRODUCTION_DAYS, SHIPPING_DAYS
    alerts = []
    for v, a in m.items():
        if a["avg_production_days"] and a["avg_production_days"] > PRODUCTION_DAYS:
            alerts.append(f"{v}: avg production {a['avg_production_days']}d exceeds "
                          f"SLA {PRODUCTION_DAYS}d")
        if a["defect_rate_pct"] >= 5:
            alerts.append(f"{v}: defect rate {a['defect_rate_pct']}% is high")
    return {"vendors": m, "overdue": late, "alerts": alerts,
            "best_vendor": best_vendor(m),
            "sla": {"production_days": PRODUCTION_DAYS, "shipping_days": SHIPPING_DAYS}}


def format_capacity_text(now: datetime | None = None) -> str:
    """Render the capacity report as plain text for console/email."""
    r = capacity_report(now)
    if not r["vendors"]:
        return ("Production Capacity Monitor\n" + "-" * 40 +
                "\nNo orders yet - vendor speed/defect metrics populate as orders "
                "are fulfilled.")
    lines = ["Production Capacity Monitor", "-" * 40,
             f"  SLA: production <= {r['sla']['production_days']}d, "
             f"shipping <= {r['sla']['shipping_days']}d"]
    for v, a in r["vendors"].items():
        lines.append(f"  {v}: {a['orders']} orders | prod "
                     f"{a['avg_production_days']}d | ship {a['avg_shipping_days']}d "
                     f"| defects {a['defect_rate_pct']}%")
    if r["overdue"]:
        lines.append(f"  OVERDUE ({len(r['overdue'])}):")
        for o in r["overdue"][:8]:
            lines.append(f"     {o['order_id']} [{o['vendor']}] {o['stage']} "
                         f"+{o['days_late']}d late")
    if r["alerts"]:
        lines.append("  ALERTS:")
        for al in r["alerts"]:
            lines.append(f"     ! {al}")
    if r["best_vendor"]:
        lines.append(f"  Recommended vendor (fastest, low defects): {r['best_vendor']}")
    return "\n".join(lines)
