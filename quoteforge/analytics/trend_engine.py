"""Trend Prediction Engine.

Combines three real signals to recommend what to make/list next:
  1. Seasonal spikes - upcoming peaks from the marketing calendar (deterministic,
     always available).
  2. Our own rising demand - occasions/themes gaining orders (from real sales).
  3. External search/Pinterest trends - pulled when a trends source is configured
     (hook), otherwise skipped (never fabricated).

Outputs holiday recommendations, new listing ideas, and new quote themes, with an
AI-written narrative when Claude is configured and a deterministic fallback.
"""
from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def seasonal_signals(now: datetime | None = None, horizon_days: int = 60) -> list[dict]:
    """Upcoming seasonal peaks worth listing/marketing for, soonest first."""
    try:
        from quoteforge.etsy.marketing_calendar import upcoming_actions
        actions = upcoming_actions(now=now, horizon_days=horizon_days)
    except Exception:  # noqa: BLE001
        return []
    seen, out = set(), []
    for a in actions:
        key = a["occasion"]
        if key in seen:
            continue
        seen.add(key)
        out.append({"occasion": a["occasion"], "days_away": a["days_away"],
                    "revenue_rank": a.get("revenue_rank", 99)})
    return out


def rising_demand(orders: list[dict] | None = None) -> list[dict]:
    """Occasions gaining orders recently vs earlier (our own demand signal)."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    rows = get_all_orders(limit=100000) if orders is None else orders
    rows = [o for o in rows if o.get("occasion")]
    if len(rows) < 4:
        return []
    rows.sort(key=lambda o: o.get("created_at") or "")
    mid = len(rows) // 2
    early, late = rows[:mid], rows[mid:]

    def _count(sample):
        """Order count per occasion within a sample of orders."""
        c: dict[str, int] = {}
        for o in sample:
            k = (o.get("occasion") or "").strip()
            if k:
                c[k] = c.get(k, 0) + 1
        return c

    e, l = _count(early), _count(late)
    rising = []
    for occ, ln in l.items():
        delta = ln - e.get(occ, 0)
        if delta > 0:
            rising.append({"occasion": occ, "recent": ln, "earlier": e.get(occ, 0),
                           "delta": delta})
    return sorted(rising, key=lambda r: r["delta"], reverse=True)


def external_trends() -> dict:
    """Pluggable external trends (Pinterest/Etsy search). Skipped if unconfigured."""
    import os
    if not (os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
            or os.getenv("ETSY_API_KEY", "").strip()):
        return {"configured": False, "terms": []}
    try:  # pragma: no cover - only with live credentials
        from quoteforge.marketing.pinterest import trending_terms
        return {"configured": True, "terms": trending_terms()}
    except Exception:  # noqa: BLE001
        return {"configured": False, "terms": []}


def predict(now: datetime | None = None) -> dict:
    """Full trend picture + concrete recommendations."""
    seasonal = seasonal_signals(now)
    rising = rising_demand()
    external = external_trends()

    listing_ideas, theme_ideas, holiday_recs = [], [], []
    for s in seasonal[:5]:
        holiday_recs.append(f"{s['occasion']} is {s['days_away']} days out - "
                            f"list/refresh now (revenue rank {s['revenue_rank']}).")
        listing_ideas.append(f"Personalized {s['occasion']} keepsake (name + date)")
        theme_ideas.append(f"{s['occasion']} sentiment quotes")
    for r in rising[:5]:
        listing_ideas.append(f"Expand {r['occasion']} range (+{r['delta']} recent orders)")

    return {"seasonal": seasonal, "rising_demand": rising, "external": external,
            "holiday_recommendations": holiday_recs,
            "new_listing_ideas": listing_ideas, "new_quote_themes": theme_ideas}


def _narrative(data: dict) -> str:
    """Short what-to-make-next summary - AI-written when Claude is configured,
    deterministic from the seasonal/rising signals otherwise."""
    facts = (f"Upcoming seasons: {[s['occasion'] for s in data['seasonal'][:5]]}; "
             f"rising occasions: {[r['occasion'] for r in data['rising_demand'][:5]]}; "
             f"external trends configured: {data['external']['configured']}.")
    try:
        from quoteforge.ai.assistant import ai_text
        text = ai_text(
            "You are a product strategist for a personalized wall-art shop. In 2-3 "
            "sentences recommend what to create/list next, using ONLY these real "
            f"signals (don't invent trends): {facts}", "trend_prediction",
            max_tokens=180)
        if text and text.strip():
            return text.strip()
    except Exception as exc:  # noqa: BLE001 - AI summary optional, deterministic fallback
        logger.debug("trend AI summary skipped: %s", exc)
    if data["seasonal"]:
        nxt = data["seasonal"][0]
        return (f"Prioritize {nxt['occasion']} ({nxt['days_away']} days out) - list "
                "and market now. " + ("Also double down on rising demand for "
                + ", ".join(r["occasion"] for r in data["rising_demand"][:3]) + "."
                if data["rising_demand"] else ""))
    return ("No imminent seasonal peaks; build evergreen ranges and revisit as "
            "order history grows.")


def format_trend_text(now: datetime | None = None) -> str:
    """Plain-text trend report: narrative, holiday recs, listing ideas."""
    d = predict(now)
    lines = ["Trend Prediction Engine", "-" * 40, _narrative(d), ""]
    if d["holiday_recommendations"]:
        lines.append("  Holiday recommendations:")
        for h in d["holiday_recommendations"]:
            lines.append(f"   - {h}")
    if d["new_listing_ideas"]:
        lines.append("  New listing ideas:")
        for i in d["new_listing_ideas"][:8]:
            lines.append(f"   - {i}")
    if not d["external"]["configured"]:
        lines.append("  (External Pinterest/Etsy search trends not connected - set "
                     "PINTEREST_ACCESS_TOKEN / ETSY_API_KEY to enrich.)")
    return "\n".join(lines)
