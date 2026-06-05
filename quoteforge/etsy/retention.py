"""Customer retention & lifetime-value engine.

The highest-leverage growth mechanic for a PERSONALIZED-gift shop: a buyer who
ordered "for my daughter's graduation" will gift that same person again - her
birthday, Christmas, the next milestone. Most shops never follow up. This engine:

  1. PREDICTS each customer's next gifting occasion for the same recipient
     (relationship-anchored calendar days + the recurring original occasion).
  2. SCHEDULES proactive repeat-gift outreach ~3 weeks before that date, with a
     fresh design idea and a loyalty coupon - turning one-time buyers into
     annual repeat buyers (the biggest driver of lifetime value).
  3. CROSS-SELLS "complete their story": the same personalized message on a
     mug / journal / ornament, to lift average order value at point of sale.
  4. WIN-BACKS lapsed customers with a tiered come-back coupon.

It reads real orders from the DB, so it gets smarter as Joffiels grows.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

# Relationship -> a fixed-calendar gifting day for that recipient.
_ANCHOR_DAY = [
    ("grandmother", "Grandparent's / Mother's Day", (5, 11)),
    ("grandma", "Grandparent's / Mother's Day", (5, 11)),
    ("grandfather", "Grandparent's / Father's Day", (6, 15)),
    ("grandpa", "Grandparent's / Father's Day", (6, 15)),
    ("mother", "Mother's Day", (5, 11)),
    ("mom", "Mother's Day", (5, 11)),
    ("father", "Father's Day", (6, 15)),
    ("dad", "Father's Day", (6, 15)),
    ("wife", "Valentine's Day", (2, 14)),
    ("husband", "Valentine's Day", (2, 14)),
]
_CHRISTMAS = ("Christmas", (12, 25))
# Occasions that recur ~yearly for the same recipient.
_RECURRING = ("birthday", "anniversary", "graduation")


@dataclass
class Coupon:
    code: str
    pct: int
    reason: str


def coupon_for(order_count: int, days_since_last: int) -> Coupon:
    """Tiered incentive based on loyalty / lapse."""
    if days_since_last > 180:
        return Coupon("COMEBACK15", 15, "win back a lapsed customer")
    if order_count >= 3:
        return Coupon("VIP15", 15, "reward a repeat VIP buyer")
    if order_count == 2:
        return Coupon("LOYAL12", 12, "thank a returning buyer")
    return Coupon("THANKYOU10", 10, "encourage a second order")


def _next_date(month: int, day: int, now: datetime) -> datetime:
    cand = datetime(now.year, month, day)
    if cand < now:
        cand = datetime(now.year + 1, month, day)
    return cand


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime((s or "")[:19], fmt)
        except (ValueError, TypeError):
            continue
    return datetime.now()


def predict_next_occasions(order: dict, now: datetime | None = None) -> list[dict]:
    """Upcoming gifting occasions for this order's recipient, soonest first."""
    now = now or datetime.now()
    rel = (order.get("relationship") or "").lower()
    occ = (order.get("occasion") or "").lower()
    out: list[dict] = []

    # Everyone gets Christmas.
    cdate = _next_date(*_CHRISTMAS[1], now)
    out.append({"occasion": _CHRISTMAS[0], "date": cdate,
                "days_away": (cdate - now).days})

    # Relationship-anchored fixed day.
    for kw, label, md in _ANCHOR_DAY:
        if kw in rel:
            d = _next_date(*md, now)
            out.append({"occasion": label, "date": d,
                        "days_away": (d - now).days})
            break

    # The original occasion, recurring ~1 year after the order.
    if any(r in occ for r in _RECURRING):
        anchor = _parse_dt(order.get("created_at", "")) + timedelta(days=365)
        while anchor < now:
            anchor += timedelta(days=365)
        out.append({"occasion": order.get("occasion", "their special day"),
                    "date": anchor, "days_away": (anchor - now).days})

    # Dedup by occasion label, keep soonest.
    best: dict[str, dict] = {}
    for o in out:
        if o["occasion"] not in best or o["days_away"] < best[o["occasion"]]["days_away"]:
            best[o["occasion"]] = o
    return sorted(best.values(), key=lambda o: o["days_away"])


def complete_the_story(order: dict, max_products: int = 3) -> dict:
    """Cross-sell the SAME personalized message on add-on products."""
    from quoteforge.etsy.product_lines import story_to_products
    products = story_to_products(order.get("occasion", ""), max_products + 2)
    # Skip prints (they already bought the wall art); push other formats.
    addons = [p for p in products if p["category"] != "print"][:max_products]
    recipient = order.get("recipient_name", "your recipient")
    names = ", ".join(p["product"] for p in addons)
    return {
        "order_id": order.get("order_id", ""),
        "recipient": recipient,
        "addons": addons,
        "extra_revenue": round(sum(p["sell_price"] for p in addons), 2),
        "message": (f"Loved your gift for {recipient}? Make it a set - the same "
                    f"personalized message looks beautiful on a {names}. "
                    f"Reply and I'll set it up at a bundle price."),
    }


def repeat_gift_outreach(orders: list[dict], now: datetime | None = None,
                         lead_days: int = 28) -> list[dict]:
    """Proactive 'gift them again' actions for occasions inside the lead window."""
    now = now or datetime.now()
    # Count orders per customer for coupon tiering.
    counts: dict[str, int] = {}
    last_seen: dict[str, datetime] = {}
    for o in orders:
        key = o.get("customer_email") or o.get("customer_name") or "?"
        counts[key] = counts.get(key, 0) + 1
        dt = _parse_dt(o.get("created_at", ""))
        if key not in last_seen or dt > last_seen[key]:
            last_seen[key] = dt

    actions: list[dict] = []
    for o in orders:
        recipient = o.get("recipient_name")
        if not recipient:
            continue
        key = o.get("customer_email") or o.get("customer_name") or "?"
        upcoming = predict_next_occasions(o, now)
        soon = next((u for u in upcoming if 0 < u["days_away"] <= lead_days), None)
        if not soon:
            continue
        days_since = (now - last_seen.get(key, now)).days
        cp = coupon_for(counts.get(key, 1), days_since)
        actions.append({
            "customer": o.get("customer_name", "Customer"),
            "recipient": recipient,
            "occasion": soon["occasion"],
            "days_away": soon["days_away"],
            "coupon": cp.code, "coupon_pct": cp.pct,
            "message": (f"Hi {o.get('customer_name','there')}! {recipient}'s "
                        f"{soon['occasion']} is coming up in {soon['days_away']} "
                        f"days. I'd love to create another personalized piece for "
                        f"them - here's {cp.pct}% off with code {cp.code}."),
        })
    actions.sort(key=lambda a: a["days_away"])
    return actions


def lapsed_customers(orders: list[dict], now: datetime | None = None,
                     days: int = 120) -> list[dict]:
    """Customers with no order in `days` - win-back candidates."""
    now = now or datetime.now()
    last: dict[str, dict] = {}
    for o in orders:
        key = o.get("customer_email") or o.get("customer_name") or "?"
        dt = _parse_dt(o.get("created_at", ""))
        if key not in last or dt > last[key]["dt"]:
            last[key] = {"dt": dt, "order": o}
    out = []
    for key, v in last.items():
        gap = (now - v["dt"]).days
        if gap >= days:
            # Lapsed by definition -> always the come-back coupon.
            out.append({"customer": v["order"].get("customer_name", "Customer"),
                        "days_since": gap, "coupon": "COMEBACK15",
                        "recipient": v["order"].get("recipient_name", "")})
    return sorted(out, key=lambda x: -x["days_since"])


def retention_digest(now: datetime | None = None) -> dict:
    """The full retention action list from live orders."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    now = now or datetime.now()
    orders = get_all_orders(limit=100000)
    billable = [o for o in orders if o.get("status") not in (None, "error")]
    outreach = repeat_gift_outreach(billable, now)
    cross = [complete_the_story(o) for o in billable
             if o.get("status") in ("shipped", "delivered")
             and not o.get("upsell_sent")][:10]
    lapsed = lapsed_customers(billable, now)
    return {"now": now.strftime("%Y-%m-%d"), "order_count": len(billable),
            "repeat_gift": outreach, "cross_sell": cross, "lapsed": lapsed,
            "potential_revenue": round(sum(c["extra_revenue"] for c in cross), 2)}


def format_retention_text(d: dict) -> str:
    lines = ["=" * 64, f"RETENTION & LTV ACTIONS  (as of {d['now']})", "=" * 64,
             f"Analyzed {d['order_count']} order(s)."]
    lines.append(f"\nREPEAT-GIFT OUTREACH ({len(d['repeat_gift'])}) - "
                 f"gift the same recipient again:")
    for a in d["repeat_gift"][:15]:
        lines.append(f"  - {a['recipient']}'s {a['occasion']} in {a['days_away']}d "
                     f"-> message {a['customer']} ({a['coupon_pct']}% {a['coupon']})")
    lines.append(f"\nCROSS-SELL 'COMPLETE THE STORY' ({len(d['cross_sell'])}) - "
                 f"+${d['potential_revenue']:.0f} potential:")
    for c in d["cross_sell"][:10]:
        names = ", ".join(p["product"] for p in c["addons"])
        lines.append(f"  - {c['recipient']}: add {names} (+${c['extra_revenue']:.0f})")
    lines.append(f"\nWIN-BACK LAPSED ({len(d['lapsed'])}):")
    for l in d["lapsed"][:10]:
        lines.append(f"  - {l['customer']} ({l['days_since']}d quiet) -> {l['coupon']}")
    lines.append("=" * 64)
    return "\n".join(lines)


def send_retention_digest(now: datetime | None = None) -> dict:
    d = retention_digest(now)
    if not (d["repeat_gift"] or d["cross_sell"] or d["lapsed"]):
        return {"status": "no_action", "digest": d}
    from quoteforge.automation.emailer import _send_email
    subject = (f"Joffiels Retention: {len(d['repeat_gift'])} repeat-gift, "
               f"{len(d['cross_sell'])} cross-sell, {len(d['lapsed'])} win-back")
    body = (f"<html><body style='font-family:Arial'><pre style='font-size:13px'>"
            f"{format_retention_text(d)}</pre></body></html>")
    out = _send_email(subject, body)
    return {"status": out["status"], "digest": d}
