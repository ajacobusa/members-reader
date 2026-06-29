"""Memory-based gift profiles - repeat-gifting reminders from saved recipients.

Buyers save the people they gift (recipient, relationship, occasion, date, notes).
Ahead of each saved date we surface a reminder so the buyer can re-gift in one
click. Reminders fire only for real saved profiles; nothing is invented.
"""
from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _days_until_anniversary(event_date: str, now: datetime) -> int | None:
    """Days until the next yearly recurrence of an ISO/MM-DD date (None if blank)."""
    s = (event_date or "").strip()
    if not s:
        return None
    parts = s.replace("/", "-").split("-")
    try:
        if len(parts) == 3:           # YYYY-MM-DD
            month, day = int(parts[1]), int(parts[2])
        elif len(parts) == 2:         # MM-DD
            month, day = int(parts[0]), int(parts[1])
        else:
            return None
        def _on(year: int) -> datetime:
            """The occasion date in the given year (Feb 29 observed on Feb 28)."""
            try:
                return datetime(year, month, day)
            except ValueError:
                # Feb 29 in a non-leap year -> observe on Feb 28
                if month == 2 and day == 29:
                    return datetime(year, 2, 28)
                raise
        this_year = _on(now.year)
        nxt = this_year if this_year.date() >= now.date() else _on(now.year + 1)
        return (nxt.date() - now.date()).days
    except (ValueError, TypeError):
        return None


def upcoming_gift_reminders(days_ahead: int = 21,
                            now: datetime | None = None) -> list[dict]:
    """Saved profiles whose occasion date falls within `days_ahead` days.

    Skips profiles already reminded for the current cycle (idempotent per year).
    """
    from quoteforge.db.database import init_db, get_gift_profiles
    init_db()
    now = now or datetime.now()
    out = []
    for p in get_gift_profiles():
        days = _days_until_anniversary(p.get("event_date", ""), now)
        if days is None or days > days_ahead:
            continue
        # idempotency: skip if already reminded within the last ~330 days
        rem = (p.get("reminded_at") or "").strip()
        if rem:
            try:
                last = datetime.fromisoformat(rem.replace("Z", ""))
                if (now - last).days < 330:
                    continue
            except ValueError as exc:
                logger.debug("unparseable last-reminded date, will remind: %s", exc)
        out.append({
            "id": p["id"], "owner_email": p["owner_email"],
            "recipient_name": p["recipient_name"],
            "relationship": p.get("relationship", ""),
            "occasion": p.get("occasion", ""),
            "event_date": p.get("event_date", ""),
            "days_away": days, "notes": p.get("notes", ""),
        })
    return sorted(out, key=lambda r: r["days_away"])


def format_reminders_text(days_ahead: int = 21,
                          now: datetime | None = None) -> str:
    """Render upcoming gift reminders as a human-readable list."""
    rem = upcoming_gift_reminders(days_ahead, now)
    if not rem:
        return ("Gift-profile reminders\n" + "-" * 40 +
                "\nNo saved gift dates coming up (or none saved yet).")
    lines = ["Gift-profile reminders (repeat gifting)", "-" * 40]
    for r in rem:
        who = f"{r['recipient_name']}" + (f" ({r['relationship']})" if r["relationship"] else "")
        lines.append(f"  in {r['days_away']:>2}d  {who} - {r['occasion'] or 'occasion'} "
                     f"[{r['owner_email']}]")
    return "\n".join(lines)
