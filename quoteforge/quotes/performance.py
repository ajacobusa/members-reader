"""Performance-ranked quote library.

Ranks quote *themes* (the order's occasion + tone) by REAL sales: how many orders
each theme produced and how much revenue. Pre-launch (no orders) it falls back to
the built-in library order, so callers always get a usable ranking - it just gets
smarter as real sales accumulate. No fabricated popularity.
"""
from __future__ import annotations


def _orders() -> list[dict]:
    """All orders from the DB (the dataset every metric reads)."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    try:
        return get_all_orders(limit=100000)
    except Exception:  # noqa: BLE001
        return []


def theme_performance(orders: list[dict] | None = None) -> list[dict]:
    """Each (occasion, tone) theme ranked by orders then revenue (real data).

    Pass `orders` (a prefetched list) to avoid re-querying the orders table.
    """
    agg: dict[tuple, dict] = {}
    for o in (_orders() if orders is None else orders):
        occ = (o.get("occasion") or "").strip() or "General"
        tone = (o.get("tone") or "").strip() or "Inspirational"
        key = (occ, tone)
        try:
            rev = float(o.get("sale_price") or 0.0)
        except (TypeError, ValueError):
            rev = 0.0
        a = agg.setdefault(key, {"occasion": occ, "tone": tone,
                                 "orders": 0, "revenue": 0.0})
        a["orders"] += 1
        a["revenue"] = round(a["revenue"] + rev, 2)
    return sorted(agg.values(),
                  key=lambda r: (r["orders"], r["revenue"]), reverse=True)


def ranked_categories() -> list[str]:
    """Quote-library categories ordered by real sales performance.

    Categories with sales come first (best-selling first); the rest follow in
    their library order so nothing is dropped. Falls back to plain library order
    when there are no sales yet.
    """
    from quoteforge.quotes.library import QUOTE_LIBRARY
    all_cats = list(QUOTE_LIBRARY.keys())
    perf = theme_performance()
    if not perf:
        return all_cats
    # Score each category by how often its name matches a selling theme.
    score: dict[str, float] = {c: 0.0 for c in all_cats}
    for row in perf:
        text = f"{row['occasion']} {row['tone']}".lower()
        for c in all_cats:
            if c.lower() in text or any(w in text for w in c.lower().split("_")):
                score[c] += row["orders"] * 10 + row["revenue"]
    return sorted(all_cats, key=lambda c: score[c], reverse=True)


def best_quotes(category: str = "", count: int = 5) -> list[str]:
    """Quotes from the best-performing category (or a specific one if given)."""
    from quoteforge.quotes.library import get_quotes
    if not category:
        cats = ranked_categories()
        category = cats[0] if cats else ""
    return get_quotes(category, count)


def format_performance_text(orders: list[dict] | None = None) -> str:
    """Human-readable quote-theme performance report (printed by the CLI)."""
    perf = theme_performance(orders)
    if not perf:
        return ("Quote performance\n" + "-" * 40 +
                "\nNo sales yet - themes will rank by real performance after your "
                "first orders. Showing library default order for now.")
    lines = ["Quote performance (by real sales)", "-" * 40,
             "  Rank  Occasion / Tone                  Orders   Revenue"]
    for i, r in enumerate(perf[:15], 1):
        label = f"{r['occasion']} / {r['tone']}"[:32]
        lines.append(f"  {i:>3}.  {label:<32} {r['orders']:>5}   "
                     f"${r['revenue']:,.2f}")
    return "\n".join(lines)
