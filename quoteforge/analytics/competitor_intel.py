"""Competitor Intelligence Dashboard.

Tracks competitor shops over time (prices, listing counts, review growth,
bestseller badges) and raises alerts when a competitor drops price, launches new
listings, or surges in reviews. Snapshots are recorded into the DB; comparing the
latest two snapshots produces the alerts.

Data sourcing: snapshots can be entered manually (admin) or pulled by an external
collector. `fetch_snapshot()` is a pluggable hook - it attempts the Etsy API when
keys are configured, otherwise it no-ops (the dashboard still works on whatever
real snapshots exist). Nothing is fabricated.
"""
from __future__ import annotations


def record(shop: str, **fields) -> int:
    """Store a competitor snapshot (thin wrapper over the DB)."""
    from quoteforge.db.database import init_db, add_competitor_snapshot
    init_db()
    return add_competitor_snapshot(shop, **fields)


def fetch_snapshot(shop: str) -> dict | None:
    """Best-effort live pull for a shop. Returns a snapshot dict or None.

    Uses the Etsy Open API when ETSY_API_KEY is set (findShops/listings). Kept
    defensive: any failure (no key, rate limit, schema change) returns None so the
    dashboard degrades to stored snapshots rather than crashing or inventing data.
    """
    import os
    if not os.getenv("ETSY_API_KEY", "").strip():
        return None
    try:  # pragma: no cover - exercised only with live credentials
        from quoteforge.automation.etsy_api import shop_public_stats
        stats = shop_public_stats(shop)
        if not stats:
            return None
        return {"shop": shop, "listings": stats.get("listing_active_count"),
                "reviews": stats.get("review_count"),
                "min_price": stats.get("min_price"),
                "avg_price": stats.get("avg_price")}
    except Exception:  # noqa: BLE001
        return None


def refresh(shops: list[str] | None = None) -> dict:
    """Pull + store a fresh snapshot for each configured competitor (if live)."""
    from quoteforge.config import COMPETITORS
    shops = shops if shops is not None else COMPETITORS
    captured = 0
    for s in shops:
        snap = fetch_snapshot(s)
        if snap:
            record(s, listings=snap.get("listings"), min_price=snap.get("min_price"),
                   avg_price=snap.get("avg_price"), reviews=snap.get("reviews"))
            captured += 1
    return {"shops": len(shops), "captured": captured}


def _delta(curr, prev):
    if curr is None or prev is None:
        return None
    return curr - prev


def alerts(shop: str = "") -> list[dict]:
    """Compare the two latest snapshots per shop and emit change alerts."""
    from quoteforge.db.database import init_db, get_competitor_snapshots
    from quoteforge.config import (COMPETITORS, COMPETITOR_PRICE_DROP_ALERT_PCT)
    init_db()
    shops = [shop] if shop else (COMPETITORS or sorted(
        {s["shop"] for s in get_competitor_snapshots()}))
    out = []
    for sh in shops:
        snaps = get_competitor_snapshots(sh)
        if len(snaps) < 2:
            continue
        prev, curr = snaps[-2], snaps[-1]
        # price drop
        pmin, cmin = prev.get("min_price"), curr.get("min_price")
        if pmin and cmin and cmin < pmin:
            drop = round((pmin - cmin) / pmin * 100, 1)
            if drop >= COMPETITOR_PRICE_DROP_ALERT_PCT:
                out.append({"shop": sh, "type": "price_drop",
                            "message": f"{sh} dropped lowest price "
                                       f"${pmin:.2f} -> ${cmin:.2f} (-{drop}%)"})
        # new listings
        dl = _delta(curr.get("listings"), prev.get("listings"))
        if dl and dl > 0:
            out.append({"shop": sh, "type": "new_listings",
                        "message": f"{sh} added {dl} new listing(s) "
                                   f"({prev.get('listings')} -> {curr.get('listings')})"})
        # review growth
        dr = _delta(curr.get("reviews"), prev.get("reviews"))
        if dr and dr > 0:
            out.append({"shop": sh, "type": "review_growth",
                        "message": f"{sh} gained {dr} review(s) - rising demand"})
        # bestseller badges
        db = _delta(curr.get("bestsellers"), prev.get("bestsellers"))
        if db and db > 0:
            out.append({"shop": sh, "type": "bestseller",
                        "message": f"{sh} now has {curr.get('bestsellers')} bestseller "
                                   f"badge(s) (+{db}) - a trend is emerging"})
    return out


def dashboard(shop: str = "") -> dict:
    from quoteforge.db.database import get_competitor_snapshots
    from quoteforge.config import COMPETITORS
    snaps = get_competitor_snapshots(shop)
    latest: dict[str, dict] = {}
    for s in snaps:
        latest[s["shop"]] = s            # last write wins (sorted ascending)
    return {"tracked": COMPETITORS, "latest": latest, "alerts": alerts(shop)}


def format_competitor_text(shop: str = "") -> str:
    d = dashboard(shop)
    if not d["latest"] and not d["tracked"]:
        return ("Competitor Intelligence\n" + "-" * 40 +
                "\nNo competitors configured. Set COMPETITORS and record snapshots "
                "(admin competitor add ...) to start tracking prices & trends.")
    lines = ["Competitor Intelligence", "-" * 40]
    if d["tracked"]:
        lines.append(f"  Tracking: {', '.join(d['tracked'])}")
    if d["latest"]:
        lines.append("  Latest snapshots:")
        for sh, s in d["latest"].items():
            lines.append(f"     {sh}: {s.get('listings')} listings, "
                         f"min ${s.get('min_price')}, {s.get('reviews')} reviews")
    else:
        lines.append("  No snapshots recorded yet.")
    if d["alerts"]:
        lines.append("  ALERTS:")
        for a in d["alerts"]:
            lines.append(f"     ! {a['message']}")
    else:
        lines.append("  No change alerts (need >=2 snapshots per shop).")
    return "\n".join(lines)
