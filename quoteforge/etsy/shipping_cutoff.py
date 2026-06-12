"""'Order by' gift-deadline banner - urgency that lifts gifting conversion.

Computes the order-by date for the next major gift occasion:
    order_by = occasion_date - (production_days + shipping_days)
and surfaces it when the occasion is near (within `within_days`).
"""
from __future__ import annotations

from datetime import date, timedelta

# (month, day, label) for fixed-date occasions. Mother's/Father's Day are
# computed (2nd Sun of May / 3rd Sun of June).
_FIXED = [(2, 14, "Valentine's Day"), (12, 25, "Christmas"),
          (12, 31, "New Year"), (11, 11, "Veterans Day"), (10, 31, "Halloween"),
          (7, 4, "Independence Day"), (3, 17, "St. Patrick's Day")]


def _nth_weekday(year, month, weekday, n):
    """Date of the nth given weekday (0=Mon) in a month."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _occasions(year):
    """All (date, label) gift occasions for a year, fixed and computed."""
    occ = [(date(year, m, d), label) for m, d, label in _FIXED]
    occ.append((_nth_weekday(year, 5, 6, 2), "Mother's Day"))   # 2nd Sun May
    occ.append((_nth_weekday(year, 6, 6, 3), "Father's Day"))   # 3rd Sun Jun
    occ.append((_nth_weekday(year, 11, 3, 4), "Thanksgiving"))  # 4th Thu Nov
    return occ


def upcoming_cutoff(today: date = None, within_days: int = 45,
                    production_days: int = None, shipping_days: int = None):
    """Return {occasion, occasion_date, order_by, days_left} for the soonest
    occasion whose ORDER-BY date is still in the future and within window."""
    from quoteforge.config import PRODUCTION_DAYS, SHIPPING_DAYS
    today = today or date.today()
    pd = PRODUCTION_DAYS if production_days is None else production_days
    sd = SHIPPING_DAYS if shipping_days is None else shipping_days
    lead = pd + sd
    cands = []
    for yr in (today.year, today.year + 1):
        for d, label in _occasions(yr):
            order_by = d - timedelta(days=lead)
            if today <= order_by <= today + timedelta(days=within_days):
                cands.append((order_by, d, label))
    if not cands:
        return None
    order_by, occ_date, label = min(cands)
    return {"occasion": label, "occasion_date": occ_date.isoformat(),
            "order_by": order_by.isoformat(),
            "days_left": (order_by - today).days}


def banner_text(cut: dict) -> str:
    """Customer-facing urgency banner line for an upcoming cutoff."""
    from datetime import date as _d
    ob = _d.fromisoformat(cut["order_by"])
    try:
        when = ob.strftime("%b ") + str(ob.day)   # Windows-safe (no %-d)
    except Exception:  # noqa: BLE001
        when = cut["order_by"]
    d = cut["days_left"]
    urgency = "Order today!" if d <= 2 else f"Only {d} days left"
    return (f"{urgency} - order by {when} to get it in time for "
            f"{cut['occasion']}.")
