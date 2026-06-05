"""Demand-driven, calendar-aware SEO agent.

Search demand for gift items spikes hard around calendar occasions. To rank when
that demand arrives you must refresh SEO BEFORE the peak — and Etsy needs ~3-4
weeks to re-rank a listing for new terms. So this agent runs two phases per peak:

  PHASE 1  SEO REFRESH      (peak - ~4 weeks): update titles/tags with the
           season's high-demand keywords so you rank as volume climbs.
  PHASE 2  LAST-MINUTE PUSH (peak - ~1 week): add "last minute / fast shipping /
           digital download" terms + raise ad budget on the in-demand items.

It also flags LOW-demand (off-season) items to de-prioritise so spend follows
demand. Designed to run weekly and email you exactly what to change, when.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from quoteforge.etsy.marketing_calendar import _next_date

# Lead windows (days before the peak).
REFRESH_WINDOW = (21, 42)      # do the SEO refresh in this band
LASTMIN_WINDOW = (2, 10)       # do the last-minute keyword + ad push here


@dataclass
class SeasonSEO:
    season: str
    peak: tuple[int, int]          # (month, day) of the demand peak
    revenue_rank: int              # 1 = biggest
    relationships: list[str]       # which relationship listings spike
    professions: bool              # do profession/graduation listings spike?
    refresh_keywords: list[str]    # add ~4 weeks out (each <=20 chars)
    lastminute_keywords: list[str] = field(default_factory=list)


# The demand map. Peaks are approximate but good enough for lead-time planning.
SEASON_SEO: list[SeasonSEO] = [
    SeasonSEO("Christmas", (12, 25), 1,
              ["Daughter", "Son", "Mom", "Dad", "Grandma", "Grandpa", "Wife", "Husband"],
              False,
              ["christmas gift", "christmas 2026", "xmas gift idea", "stocking stuffer"],
              ["last minute xmas", "digital download", "printable gift"]),
    SeasonSEO("Mother's Day", (5, 11), 2,
              ["Mom", "Grandma", "Wife"], False,
              ["mothers day gift", "mothers day 2026", "gift for mom",
               "first mothers day"],
              ["last minute mom gift", "digital mom gift", "printable mom art"]),
    SeasonSEO("Graduation", (5, 20), 3,
              ["Daughter", "Son"], True,
              ["graduation gift", "class of 2026", "grad gift idea", "senior gift"],
              ["last minute grad gift", "digital grad gift"]),
    SeasonSEO("Father's Day", (6, 15), 5,
              ["Dad", "Grandpa", "Husband"], False,
              ["fathers day gift", "fathers day 2026", "gift for dad",
               "first fathers day"],
              ["last minute dad gift", "digital dad gift"]),
    SeasonSEO("Valentine's Day", (2, 14), 6,
              ["Wife", "Husband"], False,
              ["valentines gift", "anniversary gift", "gift for him",
               "gift for her"],
              ["last minute valentine", "digital love gift"]),
    SeasonSEO("Wedding Season", (6, 15), 4,
              ["Wife", "Husband"], False,
              ["wedding gift", "engagement gift", "couples gift", "newlywed gift"],
              ["last minute wedding"]),
]


def _phase(days_to_peak: int) -> str:
    if REFRESH_WINDOW[0] <= days_to_peak <= REFRESH_WINDOW[1]:
        return "SEO REFRESH"
    if LASTMIN_WINDOW[0] <= days_to_peak <= LASTMIN_WINDOW[1]:
        return "LAST-MINUTE PUSH"
    return ""


def seasonal_seo_plan(now: datetime | None = None,
                      horizon_days: int = 50) -> dict:
    """Return the SEO actions due now + what's coming, demand-ranked."""
    now = now or datetime.now()
    due: list[dict] = []
    upcoming: list[dict] = []
    for s in SEASON_SEO:
        peak = _next_date(*s.peak, now)
        days = (peak - now).days
        if days > horizon_days:
            continue
        phase = _phase(days)
        targets = list(s.relationships) + (["all professions / graduation"]
                                           if s.professions else [])
        kws = s.refresh_keywords if phase == "SEO REFRESH" else s.lastminute_keywords
        entry = {
            "season": s.season, "peak": peak.strftime("%b %d"),
            "days_to_peak": days, "revenue_rank": s.revenue_rank,
            "phase": phase, "targets": targets, "keywords": kws,
            "action": _action_text(phase, s, days),
        }
        (due if phase else upcoming).append(entry)
    # Demand ranking: act on the nearest, highest-revenue peaks first.
    due.sort(key=lambda e: (e["days_to_peak"], e["revenue_rank"]))
    upcoming.sort(key=lambda e: e["days_to_peak"])
    deprioritize = _low_demand_now(now)
    return {"now": now.strftime("%Y-%m-%d"), "due": due,
            "upcoming": upcoming, "deprioritize": deprioritize}


def _action_text(phase: str, s: SeasonSEO, days: int) -> str:
    if phase == "SEO REFRESH":
        return (f"Refresh titles+tags for {', '.join(s.relationships)} listings "
                f"with seasonal keywords NOW ({days}d to peak gives Etsy time to "
                f"rank). Run `admin seo rel <Relationship> {s.season}`.")
    if phase == "LAST-MINUTE PUSH":
        return (f"Add last-minute/fast-ship/digital keywords and raise ad budget "
                f"on {', '.join(s.relationships)} ({days}d to peak).")
    return f"Monitor — {s.season} peak in {days} days."


def _low_demand_now(now: datetime) -> list[str]:
    """Seasons whose peak is far away — don't spend ads there now."""
    far = []
    for s in SEASON_SEO:
        days = (_next_date(*s.peak, now) - now).days
        if days > 90:
            far.append(f"{s.season} (peak {days}d away)")
    return far


def format_seasonal_seo(plan: dict) -> str:
    lines = ["=" * 64, f"DEMAND-DRIVEN SEO PLAN  (as of {plan['now']})", "=" * 64]
    if plan["due"]:
        lines.append("ACTION DUE NOW (demand-ranked):")
        for e in plan["due"]:
            lines.append(f"\n  [{e['phase']}] {e['season']} - peak {e['peak']} "
                         f"({e['days_to_peak']}d)")
            lines.append(f"    Targets : {', '.join(e['targets'])}")
            lines.append(f"    Keywords: {', '.join(e['keywords'])}")
            lines.append(f"    -> {e['action']}")
    else:
        lines.append("No SEO refresh or last-minute push due right now.")
    if plan["upcoming"]:
        lines.append("\nCOMING UP (prepare):")
        for e in plan["upcoming"]:
            lines.append(f"  - {e['season']}: peak {e['peak']} ({e['days_to_peak']}d)")
    if plan["deprioritize"]:
        lines.append("\nDE-PRIORITISE (off-season - no ad spend now):")
        for d in plan["deprioritize"]:
            lines.append(f"  - {d}")
    lines.append("=" * 64)
    return "\n".join(lines)


def send_seasonal_seo(now: datetime | None = None) -> dict:
    """Email the plan, but only if there's an action due (avoids noise)."""
    plan = seasonal_seo_plan(now)
    if not plan["due"]:
        return {"status": "no_action", "plan": plan}
    from quoteforge.automation.emailer import _send_email
    top = plan["due"][0]
    subject = (f"Joffiels SEO: {top['phase']} for {top['season']} "
               f"({top['days_to_peak']}d to peak)")
    body = (f"<html><body style='font-family:Arial'><pre style='font-size:13px'>"
            f"{format_seasonal_seo(plan)}</pre></body></html>")
    out = _send_email(subject, body)
    return {"status": out["status"], "plan": plan}
