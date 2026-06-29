"""Customer Journey Analysis - turns Clarity + our own funnel data into a weekly
AI summary of where shoppers struggle.

Two real data sources:
  1. Microsoft Clarity live insights (rage clicks, dead clicks, scroll depth,
     quick-backs) via the Data Export API when CLARITY_API_TOKEN is set.
  2. Our OWN funnel signal: abandoned_customizations - which listing/step shoppers
     start but don't finish (always available, no third party).

Produces a short narrative ("X% of started designs are abandoned on ...") with an
AI summary when Claude is configured, deterministic otherwise. Never invents data.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _clarity_metrics() -> dict:
    """Reuse the analytics_report Clarity block (live insights or status)."""
    try:
        from quoteforge.automation.analytics_report import _clarity_block
        return _clarity_block()
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "note": f"unavailable ({type(exc).__name__})"}


def _own_funnel() -> dict:
    """Abandonment signal we own: abandoned customizations by listing + photo step."""
    from quoteforge.db.database import (init_db, get_open_customizations,
                                        get_all_orders)
    init_db()
    try:
        open_c = get_open_customizations()
    except Exception:  # noqa: BLE001
        open_c = []
    started = len(open_c)
    with_photo = sum(1 for c in open_c if c.get("has_photo"))
    with_wording = sum(1 for c in open_c if (c.get("wording") or "").strip())
    by_listing: dict[str, int] = {}
    for c in open_c:
        key = (c.get("listing") or "(unspecified)").strip() or "(unspecified)"
        by_listing[key] = by_listing.get(key, 0) + 1
    try:
        orders = [o for o in get_all_orders(limit=100000)
                  if o.get("sale_price") not in (None, 0)]
    except Exception:  # noqa: BLE001
        orders = []
    converted = len(orders)
    total_starts = started + converted
    abandon_rate = round(started / total_starts * 100, 1) if total_starts else 0.0
    return {
        "started_open": started, "converted": converted,
        "abandon_rate_pct": abandon_rate,
        "abandoned_with_photo": with_photo,
        "abandoned_with_wording": with_wording,
        "top_abandoned_listings": sorted(by_listing.items(),
                                         key=lambda kv: kv[1], reverse=True)[:5],
    }


def journey_summary() -> dict:
    """Combine Clarity metrics and our own funnel data into one dict."""
    return {"clarity": _clarity_metrics(), "funnel": _own_funnel()}


def _ai_narrative(data: dict) -> str:
    """Short CRO narrative from the real funnel numbers - AI when available,
    deterministic fallback otherwise."""
    f = data["funnel"]
    facts = (f"Abandoned designs (open): {f['started_open']}; converted: "
             f"{f['converted']}; abandon rate: {f['abandon_rate_pct']}%; "
             f"abandoned-with-photo: {f['abandoned_with_photo']}; "
             f"top abandoned listings: {f['top_abandoned_listings']}.")
    try:
        from quoteforge.ai.assistant import ai_text
        text = ai_text(
            "You are a CRO analyst. In 2-3 sentences, summarize where shoppers "
            "struggle and the single highest-impact fix, using ONLY these real "
            f"numbers (do not invent any): {facts}",
            "journey_analysis", max_tokens=180)
        if text and text.strip():
            return text.strip()
    except Exception as exc:  # noqa: BLE001 - AI summary optional, deterministic fallback
        logger.debug("journey AI summary skipped: %s", exc)
    if f["abandon_rate_pct"] >= 50 and f["started_open"]:
        return (f"{f['abandon_rate_pct']}% of started designs are abandoned. "
                "Focus on the customization step - the recovery email + a simpler "
                "frame/size picker are the highest-impact fixes.")
    if f["converted"] == 0 and f["started_open"] == 0:
        return ("No funnel activity yet - this report becomes actionable once "
                "shoppers begin designing and ordering.")
    return (f"Abandon rate {f['abandon_rate_pct']}% across "
            f"{f['converted'] + f['started_open']} design starts. Keep monitoring "
            "rage/dead clicks in Clarity for friction points.")


def format_journey_text() -> str:
    """Render the journey analysis (narrative + funnel + Clarity) as plain text."""
    data = journey_summary()
    f, cl = data["funnel"], data["clarity"]
    lines = ["Customer Journey Analysis", "-" * 40, _ai_narrative(data), "",
             "  Our funnel (owned data):",
             f"    Designs started but open : {f['started_open']}",
             f"    Designs converted        : {f['converted']}",
             f"    Abandon rate             : {f['abandon_rate_pct']}%",
             f"    Abandoned w/ photo       : {f['abandoned_with_photo']}",
             f"    Abandoned w/ wording     : {f['abandoned_with_wording']}"]
    if f["top_abandoned_listings"]:
        lines.append("    Top abandoned listings   :")
        for name, n in f["top_abandoned_listings"]:
            lines.append(f"       {name[:30]:<30} {n}")
    if cl.get("metrics"):
        lines.append(f"  Clarity (live)           : {cl['metrics']}")
    elif cl.get("configured"):
        lines.append("  Clarity                  : configured (set CLARITY_API_TOKEN "
                     "for rage/dead-click metrics)")
    else:
        lines.append("  Clarity                  : not connected (heatmaps/rage "
                     "clicks available once CLARITY_PROJECT_ID + token are set)")
    return "\n".join(lines)
