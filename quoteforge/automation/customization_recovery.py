"""Abandoned-customization recovery.

When a shopper starts a design (picks a frame, types wording, uploads a photo)
and leaves without ordering, we save that state. This module finds those open
customizations after a quiet period and sends a gentle "your custom artwork is
still waiting" recovery email (AI-personalized when available, deterministic
otherwise). Idempotent: a customization is only recovered once unless reopened.
"""
from __future__ import annotations
from datetime import datetime

# Wait this long after the last edit before a customization counts as abandoned.
ABANDON_AFTER_MINUTES = 60
# Escalation: stage 1 fires at ABANDON_AFTER_MINUTES, then 24h and 72h. Each
# stage sends ONCE (tracked by recovery_stage). Later stages are a touch more
# urgent in tone.
_LATER_STAGES = [(1440, 2), (4320, 3)]   # (minutes, stage)
_STAGE_SUBJECT = {
    1: "Your custom artwork is still waiting",
    2: "Still thinking it over? Your design is saved",
    3: "Last chance - your saved design before it expires",
}


def _due_stage(item: dict, age_min: float, first_threshold: float) -> int:
    """The recovery stage now due for an item (0 = none), given its age and the
    stage-1 threshold. Only advances past the stage already sent."""
    current = item.get("recovery_stage") or 0
    due = 0
    for mins, stage in [(first_threshold, 1)] + _LATER_STAGES:
        if age_min >= mins and stage > current:
            due = stage
    return due


def _recovery_message(item: dict) -> str:
    """Personalized recovery copy. Uses Claude when configured; else a template."""
    listing = item.get("listing") or "your custom piece"
    material = item.get("material") or ""
    wording = (item.get("wording") or "").strip()
    try:
        from quoteforge.ai.assistant import ai_text
        prompt = (
            "Write a short, warm 2-sentence reminder email body (no subject) to a "
            "shopper who started personalizing wall art but didn't finish. "
            f"They were designing: {listing}"
            + (f", material/frame: {material}" if material else "")
            + (f", with the words: \"{wording[:80]}\"" if wording else "")
            + ". Encourage them to finish; mention a free proof before printing. "
            "No emojis, no fake discounts.")
        text = ai_text(prompt, "customization_recovery", max_tokens=160)
        if text and text.strip():
            return text.strip()
    except Exception:  # noqa: BLE001
        pass
    bits = f" ({material})" if material else ""
    extra = f' Your words “{wording[:60]}” are saved.' if wording else ""
    return (f"Your custom artwork{bits} is still waiting. Pick up right where you "
            f"left off on {listing} - and remember, we send a free digital proof "
            f"before anything is printed.{extra}")


def pending_recoveries(older_than_minutes: int = ABANDON_AFTER_MINUTES,
                       now: datetime | None = None) -> list[dict]:
    """Open customizations due for their NEXT recovery stage (1h/24h/72h), each
    annotated with `next_stage`. Read-only - does not advance anything."""
    from quoteforge.db.database import init_db, get_open_customizations
    init_db()
    now = now or datetime.now()
    out = []
    for it in get_open_customizations(0):     # all open; stage gating is here
        try:
            upd = datetime.fromisoformat((it.get("updated_at") or "").replace("Z", ""))
        except ValueError:
            continue
        age_min = (now - upd).total_seconds() / 60.0
        stage = _due_stage(it, age_min, older_than_minutes)
        if stage:
            out.append({**it, "next_stage": stage})
    return out


def run_recovery(older_than_minutes: int = ABANDON_AFTER_MINUTES,
                 send: bool = False) -> dict:
    """Escalating recovery: each due customization gets its next-stage email
    (send=True also advances the stage so it fires once). send=False is a
    read-only preview (lists candidates, advances nothing)."""
    from quoteforge.db.database import advance_recovery_stage
    items = pending_recoveries(older_than_minutes)
    sent = 0
    results = []
    for it in items:
        stage = it.get("next_stage", 1)
        msg = _recovery_message(it)
        if send:
            try:
                from quoteforge.automation.emailer import _send_email
                html = (f"<html><body style='font-family:Arial'>"
                        f"<p>{msg}</p></body></html>")
                _send_email(_STAGE_SUBJECT.get(stage, _STAGE_SUBJECT[1]),
                            html, to=it["email"])
            except Exception:  # noqa: BLE001
                pass
            # Advance regardless of email outcome so a stage never repeats
            # forever on a transient send failure.
            advance_recovery_stage(it["email"], it.get("listing", ""), stage)
            sent += 1
        results.append({"email": it["email"], "listing": it.get("listing", ""),
                        "stage": stage, "message": msg})
    return {"candidates": len(items), "sent": sent, "results": results}


def format_recovery_text(older_than_minutes: int = ABANDON_AFTER_MINUTES) -> str:
    """List abandoned designs awaiting recovery as plain text (dry run, no emails)."""
    r = run_recovery(older_than_minutes, send=False)
    if not r["candidates"]:
        return ("Abandoned customization recovery\n" + "-" * 40 +
                "\nNo abandoned designs waiting to recover.")
    lines = ["Abandoned customization recovery", "-" * 40,
             f"  {r['candidates']} design(s) waiting to recover:"]
    for it in r["results"]:
        lines.append(f"   - {it['email']} :: {it['listing'] or '(listing)'}")
    return "\n".join(lines)
