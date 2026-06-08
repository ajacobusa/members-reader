"""Customer Preference Graph - a data moat built from REAL orders.

Learns associations between what buyers choose: occasion, relationship, material,
size, tone, scenery. Answers questions like "customers buying anniversary gifts
prefer walnut frames 64% of the time" and powers data-driven recommendations.
Everything is derived from real order history - no assumptions, no fabrication.
"""
from __future__ import annotations
from collections import defaultdict

# Which order fields we treat as preference signals.
SIGNALS = ("occasion", "relationship", "material", "size", "tone", "scenery")
# Default "context -> choice" pairs we summarize (the high-value questions).
DEFAULT_PAIRS = (
    ("occasion", "material"),
    ("relationship", "material"),
    ("occasion", "tone"),
    ("occasion", "size"),
    ("relationship", "tone"),
)


def _orders(orders: list[dict] | None = None) -> list[dict]:
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    return get_all_orders(limit=100000) if orders is None else orders


def _clean(v) -> str:
    return (str(v).strip() if v is not None else "")


def distribution(context_field: str, choice_field: str,
                 orders: list[dict] | None = None,
                 min_support: int = 1) -> list[dict]:
    """For each context value, the distribution of choices with the top pick + %.

    Returns rows sorted by support (number of orders), most-evidenced first.
    `min_support` drops contexts with too few orders to be meaningful.
    """
    if context_field not in SIGNALS or choice_field not in SIGNALS:
        raise ValueError("fields must be preference signals")
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for o in _orders(orders):
        ctx = _clean(o.get(context_field))
        choice = _clean(o.get(choice_field))
        if not ctx or not choice:
            continue
        buckets[ctx][choice] += 1
    rows = []
    for ctx, choices in buckets.items():
        support = sum(choices.values())
        if support < min_support:
            continue
        top_choice, top_n = max(choices.items(), key=lambda kv: kv[1])
        rows.append({
            "context": ctx, "support": support,
            "top_choice": top_choice,
            "top_pct": round(top_n / support * 100, 1),
            "distribution": dict(sorted(choices.items(),
                                        key=lambda kv: kv[1], reverse=True)),
        })
    return sorted(rows, key=lambda r: r["support"], reverse=True)


def preferred_for(occasion: str = "", relationship: str = "",
                  choice_field: str = "material",
                  orders: list[dict] | None = None) -> dict | None:
    """The most common choice (e.g. material) for a context, with confidence.

    Prefers the most specific match available (occasion+relationship), then falls
    back to occasion alone, then relationship alone. Returns None if no evidence.
    """
    rows = _orders(orders)

    def _top(filt) -> dict | None:
        choices: dict[str, int] = defaultdict(int)
        for o in rows:
            if not filt(o):
                continue
            c = _clean(o.get(choice_field))
            if c:
                choices[c] += 1
        if not choices:
            return None
        support = sum(choices.values())
        top, n = max(choices.items(), key=lambda kv: kv[1])
        return {"choice": top, "confidence_pct": round(n / support * 100, 1),
                "support": support}

    occ, rel = _clean(occasion).lower(), _clean(relationship).lower()
    if occ and rel:
        r = _top(lambda o: _clean(o.get("occasion")).lower() == occ
                 and _clean(o.get("relationship")).lower() == rel)
        if r:
            r["basis"] = "occasion+relationship"
            return r
    if occ:
        r = _top(lambda o: _clean(o.get("occasion")).lower() == occ)
        if r:
            r["basis"] = "occasion"
            return r
    if rel:
        r = _top(lambda o: _clean(o.get("relationship")).lower() == rel)
        if r:
            r["basis"] = "relationship"
            return r
    return None


def build_graph(orders: list[dict] | None = None,
                min_support: int = 2) -> dict:
    """All default context->choice distributions + human-readable insights."""
    rows = _orders(orders)
    pairs = {}
    insights = []
    for ctx, choice in DEFAULT_PAIRS:
        dist = distribution(ctx, choice, rows, min_support=min_support)
        pairs[f"{ctx}->{choice}"] = dist
        for d in dist[:5]:
            insights.append(
                f"Customers buying {d['context']} gifts prefer "
                f"{d['top_choice']} ({d['top_pct']}% of {d['support']} orders) "
                f"[{ctx}->{choice}]")
    return {"orders_analyzed": len([o for o in rows if o.get("occasion")]),
            "pairs": pairs, "insights": insights}


def format_graph_text(orders: list[dict] | None = None,
                      min_support: int = 2) -> str:
    g = build_graph(orders, min_support=min_support)
    if not g["insights"]:
        return ("Customer Preference Graph\n" + "-" * 40 +
                "\nNot enough order history yet - preferences emerge as real "
                "orders accumulate (need >=2 orders per context).")
    lines = ["Customer Preference Graph (data moat)", "-" * 40,
             f"  Orders analyzed: {g['orders_analyzed']}", ""]
    for ins in g["insights"][:20]:
        lines.append(f"  - {ins}")
    return "\n".join(lines)
