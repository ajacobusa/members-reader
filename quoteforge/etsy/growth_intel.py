"""Growth intelligence agent - what to make MORE of, and what to drop.

The launch strategy is: ship 20, see what sells, double down on winners, retire
losers. This agent closes that loop. It reads real orders, measures revenue +
profit + velocity per segment (occasion / relationship), then recommends:

  * SCALE  the winners - concrete new listings to add (via the launch scaler)
  * RETIRE/REFRESH the losers - stop spending attention/ads there
  * FILL   demand gaps - high-revenue calendar categories you're not selling yet

Until there's enough sales data it degrades to the launch plan, so it's useful
from day one and gets sharper as Joffiels grows.
"""
from datetime import datetime

MIN_ORDERS_FOR_SIGNAL = 10   # below this, recommend the launch plan, not analytics


def _billable(orders: list[dict]) -> list[dict]:
    return [o for o in orders if o.get("status") not in (None, "error", "received")]


def segment_performance(orders: list[dict]) -> dict:
    """Revenue/profit/orders per occasion and per relationship."""
    from quoteforge.etsy.financials import order_financials
    dims = {"occasion": {}, "relationship": {}}
    for o in orders:
        fin = order_financials(o)
        for dim, key in (("occasion", o.get("occasion") or "Unknown"),
                         ("relationship", o.get("relationship") or "Unknown")):
            s = dims[dim].setdefault(key, {"orders": 0, "revenue": 0.0, "profit": 0.0})
            s["orders"] += 1
            s["revenue"] = round(s["revenue"] + fin["sale_price"], 2)
            s["profit"] = round(s["profit"] + fin["net_profit"], 2)
    return dims


def _ranked(seg: dict) -> list[tuple[str, dict]]:
    return sorted(seg.items(), key=lambda kv: kv[1]["profit"], reverse=True)


def growth_actions(now: datetime | None = None,
                   min_orders: int = MIN_ORDERS_FOR_SIGNAL) -> dict:
    """The prioritized growth recommendations from live orders."""
    from quoteforge.db.database import init_db, get_all_orders
    from quoteforge.etsy.launch_pack import current_phase, next_additions, LAUNCH_PACK_20
    init_db()
    now = now or datetime.now()
    orders = _billable(get_all_orders(limit=100000))

    # Not enough signal yet -> follow the launch/scale plan.
    if len(orders) < min_orders:
        phase = current_phase(len(LAUNCH_PACK_20))
        return {
            "phase": "launch", "orders": len(orders),
            "message": (f"Only {len(orders)} sales so far (need >= {min_orders} for "
                        f"reliable signal). Stay on the launch plan: validate the 20, "
                        f"then `admin launch scale`."),
            "next_listings": next_additions(len(LAUNCH_PACK_20), batch=5),
            "scale": [], "retire": [], "gaps": [],
        }

    perf = segment_performance(orders)
    rel = _ranked(perf["relationship"])
    occ = _ranked(perf["occasion"])

    winners = [{"segment": k, **v} for k, v in (rel[:3] + occ[:3])]
    # Losers: segments with orders but in the bottom third by profit.
    bottom = [{"segment": k, **v} for k, v in (rel[3:] + occ[3:])
              if v["orders"] >= 1 and v["profit"] < (winners[0]["profit"] * 0.25
                                                     if winners else 0)]

    # Demand gaps: high-revenue calendar categories with little/no presence.
    from quoteforge.etsy.marketing_calendar import HIGH_REVENUE_CATEGORIES
    present = {k.lower() for k in perf["occasion"]}
    gaps = [c for c in HIGH_REVENUE_CATEGORIES
            if not any(c.lower() in p for p in present)]

    return {
        "phase": "scaling", "orders": len(orders),
        "message": f"{len(orders)} sales analyzed - double down on winners.",
        "scale": winners,
        "retire": bottom[:5],
        "gaps": gaps[:5],
        "performance": perf,
    }


def format_growth_text(g: dict) -> str:
    lines = ["=" * 64, f"GROWTH INTELLIGENCE  (phase: {g['phase']}, "
             f"{g['orders']} orders)", "=" * 64, g["message"]]
    if g["phase"] == "launch":
        lines.append("\nNEXT LISTINGS TO ADD (from the scaler):")
        for n in g["next_listings"]:
            lines.append(f"  - {n['title']}")
    else:
        lines.append("\nSCALE THESE WINNERS (most profit):")
        for w in g["scale"]:
            lines.append(f"  + {w['segment']:24} {w['orders']} orders, "
                         f"${w['profit']:.0f} profit  -> add variations")
        if g["retire"]:
            lines.append("\nDE-PRIORITISE / REFRESH (low return):")
            for r in g["retire"]:
                lines.append(f"  - {r['segment']:24} {r['orders']} orders, "
                             f"${r['profit']:.0f} profit")
        if g["gaps"]:
            lines.append("\nDEMAND GAPS TO FILL (high-revenue, low presence):")
            for c in g["gaps"]:
                lines.append(f"  * {c}")
    lines.append("=" * 64)
    return "\n".join(lines)


def send_growth_report(now: datetime | None = None) -> dict:
    g = growth_actions(now)
    from quoteforge.automation.emailer import _send_email
    subject = f"Joffiels Growth Intelligence ({g['phase']}, {g['orders']} orders)"
    body = (f"<html><body style='font-family:Arial'><pre style='font-size:13px'>"
            f"{format_growth_text(g)}</pre></body></html>")
    out = _send_email(subject, body)
    return {"status": out["status"], "growth": g}
