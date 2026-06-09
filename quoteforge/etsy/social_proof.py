"""Social proof + customer gallery - REAL DATA ONLY.

No fabricated numbers, badges, or "as seen in" claims. Every stat is read from
the database and a row is rendered only when its real count is greater than zero.
Pre-launch (empty DB) the whole bar and gallery render as "" and disappear from
the page. This keeps the storefront honest while the business has no history.
"""
from __future__ import annotations


def social_proof_stats() -> dict:
    """Real counts pulled from the DB (all zero pre-launch)."""
    from quoteforge.db.database import (init_db, get_order_stats,
                                        subscriber_count, review_stats)
    init_db()
    orders = 0
    try:
        orders = int(get_order_stats().get("total", 0) or 0)
    except Exception:  # noqa: BLE001
        orders = 0
    try:
        subs = int(subscriber_count() or 0)
    except Exception:  # noqa: BLE001
        subs = 0
    rv = review_stats()
    return {"orders": orders, "subscribers": subs,
            "reviews": int(rv.get("count", 0) or 0),
            "avg": float(rv.get("avg", 0.0) or 0.0)}


# Don't advertise tiny counts - "9 pieces" / "1 on the insider list" reads weaker
# than saying nothing. Only surface a volume stat once it's genuinely reassuring.
# (Honest: we never invent numbers; we just stay quiet until they're meaningful.)
MIN_ORDERS_TO_SHOW = 25
MIN_SUBSCRIBERS_TO_SHOW = 25


def social_proof_bar() -> str:
    """A thin bar of real stats. Returns '' when there's nothing real to show."""
    s = social_proof_stats()
    items = []
    if s["orders"] >= MIN_ORDERS_TO_SHOW:
        items.append(f'<span class="spi"><b>{s["orders"]:,}</b> made-to-order pieces</span>')
    if s["reviews"] > 0:  # real reviews are strong proof even in small numbers
        stars = "★" * int(round(s["avg"]))
        items.append(f'<span class="spi"><b>{s["avg"]}</b> {stars} '
                     f'from {s["reviews"]} verified review'
                     f'{"s" if s["reviews"] != 1 else ""}</span>')
    if s["subscribers"] >= MIN_SUBSCRIBERS_TO_SHOW:
        items.append(f'<span class="spi"><b>{s["subscribers"]:,}</b> on the insider list</span>')
    if not items:
        return ""
    return f'<div class="sproof">{"".join(items)}</div>'


def customer_gallery() -> str:
    """Real customer photos only (from published reviews that include a photo).

    Returns '' when no real customer photos exist yet. A submission CTA is shown
    only alongside real photos so the section never looks empty/fake pre-launch.
    """
    from quoteforge.db.database import init_db, get_published_reviews
    init_db()
    photos = [r for r in get_published_reviews(60) if r.get("photo_url")]
    if not photos:
        return ""
    tiles = "".join(
        f'<figure class="gtile"><img src="{r["photo_url"]}" loading="lazy" '
        f'alt="Customer photo"><figcaption>{(r.get("customer_name") or "Customer")}'
        f'{" &middot; ✓" if r.get("verified") else ""}</figcaption></figure>'
        for r in photos[:12])
    return (
        '<div class="cgallery"><h2>From our customers&#39; walls</h2>'
        '<p class="csub">Real photos shared by buyers (with permission).</p>'
        f'<div class="ggrid">{tiles}</div>'
        '<p class="cshare">Tag us or reply to your delivery email to be '
        'featured here.</p></div>')
