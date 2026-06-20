"""Automated A/B testing - assign variants, track conversions, pick winners.

Experiments are defined here (single source of truth) and injected into the
storefront, which assigns each visitor a variant, records an impression, and
records a conversion when they add to their order or sign up. This module
aggregates the real events and declares a winner once there's enough data.
"""
from __future__ import annotations

# Experiment definitions. Each variant's first entry is the control.
# `apply` tells the storefront what to change (target element + value).
EXPERIMENTS = {
    "hero_headline": {
        "label": "Hero headline",
        "target": "hero_h1",
        "variants": {
            "A": "Personalized gifts for life's most meaningful moments",
            "B": "Turn your words into a gift they'll treasure forever",
            "C": "Custom wall art & apparel - made to order, just for them",
        },
    },
}

# Need at least this many impressions per variant before declaring a winner.
MIN_SAMPLE = 500


def experiments_config() -> dict:
    """Compact config for the storefront (keys, targets, variant text)."""
    return {k: {"target": v["target"], "variants": v["variants"]}
            for k, v in EXPERIMENTS.items()}


def experiment_stats(experiment: str) -> dict:
    """Impressions, conversions, and conversion rate per variant + winner."""
    from quoteforge.db.database import init_db, get_ab_events
    init_db()
    events = get_ab_events(experiment)
    variants = list(EXPERIMENTS.get(experiment, {}).get("variants", {}).keys())
    stats = {v: {"variant": v, "impressions": 0, "conversions": 0,
                 "cvr_pct": 0.0} for v in variants}
    for e in events:
        v = e.get("variant")
        if v not in stats:
            stats[v] = {"variant": v, "impressions": 0, "conversions": 0, "cvr_pct": 0.0}
        if e.get("event") == "impression":
            stats[v]["impressions"] += 1
        elif e.get("event") == "conversion":
            stats[v]["conversions"] += 1
    for s in stats.values():
        s["cvr_pct"] = round(s["conversions"] / s["impressions"] * 100, 2) \
            if s["impressions"] else 0.0
    rows = sorted(stats.values(), key=lambda s: s["cvr_pct"], reverse=True)
    # A winner needs every variant to have hit MIN_SAMPLE impressions.
    ready = all(s["impressions"] >= MIN_SAMPLE for s in rows) and len(rows) >= 2
    winner = rows[0]["variant"] if (ready and rows[0]["impressions"]) else None
    return {"experiment": experiment, "variants": rows, "winner": winner,
            "ready": ready, "min_sample": MIN_SAMPLE}


def all_stats() -> dict:
    """Cumulative A/B stats for every experiment key."""
    return {k: experiment_stats(k) for k in EXPERIMENTS}


def format_ab_text() -> str:
    """Plain-text A/B testing report for the analytics dashboard."""
    data = all_stats()
    lines = ["Automated A/B testing", "-" * 40]
    any_data = False
    for key, s in data.items():
        lines.append(f"  {EXPERIMENTS[key]['label']} [{key}]:")
        for v in s["variants"]:
            any_data = any_data or v["impressions"] > 0
            lines.append(f"     {v['variant']}: {v['impressions']} impr, "
                         f"{v['conversions']} conv ({v['cvr_pct']}%)")
        if s["winner"]:
            lines.append(f"     -> WINNER: {s['winner']}")
        elif not s["ready"]:
            lines.append(f"     (need >= {s['min_sample']} impressions/variant)")
    if not any_data:
        lines.append("  No A/B data yet - variants are live and collecting.")
    return "\n".join(lines)
