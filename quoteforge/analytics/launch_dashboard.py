"""Launch Metrics Dashboard - the one screen to watch after publishing on Etsy.

Aggregates the launch KPIs the owner ranked as mattering most:
  Views, Favorites, Conversion rate, Revenue, Profit,
  Best-performing keywords, Best-performing occasions.

Revenue/profit/occasions come from the orders DB (source of truth). Views and
favorites are listing-level stats Etsy exposes in Shop Manager; until the Etsy
API is connected they can be entered with `record_listing_stats()` (or the
`launch-dash record` CLI) so conversion is computed from real numbers - never
fabricated. Keywords are mined from the titles of SOLD orders (what actually
converted, not what we guessed).

Run:  python -m quoteforge.admin launch-dash                # print the dashboard
      python -m quoteforge.admin launch-dash record "<listing>" <views> <favs>
"""
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

# Stats Etsy shows in Shop Manager, keyed by listing title -> {views, favorites}.
_STATS_FILE = "etsy_listing_stats.json"
# Words too generic to be a "winning keyword" on their own.
_STOP = {"personalized", "gift", "custom", "print", "wall", "art", "for",
         "the", "a", "of", "with", "poster", "quote"}


def _stats_path() -> Path:
    """Where the manually-recorded Etsy view/favorite stats live (OUTPUT_DIR)."""
    from quoteforge.config import OUTPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / _STATS_FILE


def record_listing_stats(listing: str, views: int, favorites: int) -> dict:
    """Save (or update) one listing's Etsy views/favorites. Returns all stats."""
    p = _stats_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data[listing] = {"views": int(views), "favorites": int(favorites),
                     "updated": datetime.now().isoformat(timespec="seconds")}
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def _keywords(titles: list[str], top: int = 8) -> list[tuple[str, int]]:
    """Most frequent meaningful words across SOLD listing titles."""
    words = Counter()
    for t in titles:
        for w in re.findall(r"[a-z']+", t.lower()):
            if w not in _STOP and len(w) > 2:
                words[w] += 1
    return words.most_common(top)


def launch_metrics() -> dict:
    """Compute every launch KPI from the DB + recorded Etsy stats."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    orders = [o for o in get_all_orders()
              if (o.get("status") or "") not in ("cancelled", "error")]
    revenue = sum(float(o.get("sale_price") or 0) for o in orders)
    cost = sum(float(o.get("gelato_cost") or 0) for o in orders)
    fees = revenue * 0.065 + 0.20 * len(orders)      # Etsy txn + listing fees
    profit = revenue - cost - fees
    # Views/favorites from the recorded Etsy stats (real numbers only).
    p = _stats_path()
    stats = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    views = sum(s["views"] for s in stats.values())
    favs = sum(s["favorites"] for s in stats.values())
    conv = round(len(orders) / views * 100, 2) if views else None
    occ = Counter((o.get("occasion") or "unknown").strip().lower()
                  for o in orders)
    return {"as_of": datetime.now().isoformat(timespec="seconds"),
            "orders": len(orders), "views": views, "favorites": favs,
            "conversion_pct": conv, "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "margin_pct": round(profit / revenue * 100) if revenue else 0,
            "keywords": _keywords([o.get("product_title") or "" for o in orders]),
            "occasions": occ.most_common(8),
            "listings_tracked": len(stats)}


def format_dashboard(m: dict) -> str:
    """Render the dashboard for the terminal / daily email (ASCII-safe)."""
    conv = f"{m['conversion_pct']}%" if m["conversion_pct"] is not None else \
        "n/a (record views: launch-dash record \"<listing>\" <views> <favs>)"
    lines = ["=" * 58, f"LAUNCH DASHBOARD - {m['as_of']}", "=" * 58,
             f"  Views      : {m['views']:,}   ({m['listings_tracked']} listing(s) tracked)",
             f"  Favorites  : {m['favorites']:,}",
             f"  Orders     : {m['orders']:,}",
             f"  Conversion : {conv}",
             f"  Revenue    : ${m['revenue']:,.2f}",
             f"  Profit     : ${m['profit']:,.2f}  ({m['margin_pct']}% margin)",
             "  Top keywords (from SOLD titles):"]
    lines += [f"    {w:<16} x{n}" for w, n in m["keywords"]] or ["    (no sales yet)"]
    lines.append("  Top occasions:")
    lines += [f"    {o:<16} x{n}" for o, n in m["occasions"]] or ["    (no sales yet)"]
    lines.append("=" * 58)
    return "\n".join(lines)
