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
# Don't re-pester: only one recovery email per open customization.


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
    """Open customizations idle long enough to recover and not yet recovered."""
    from quoteforge.db.database import init_db, get_open_customizations
    init_db()
    items = get_open_customizations(older_than_minutes)
    return [it for it in items if not (it.get("recovered_at") or "").strip()]


def run_recovery(older_than_minutes: int = ABANDON_AFTER_MINUTES,
                 send: bool = False) -> dict:
    """Find abandoned customizations and (optionally) email each shopper once."""
    from quoteforge.db.database import mark_customization
    items = pending_recoveries(older_than_minutes)
    sent = 0
    results = []
    for it in items:
        msg = _recovery_message(it)
        if send:
            try:
                from quoteforge.automation.emailer import _send_email
                html = (f"<html><body style='font-family:Arial'>"
                        f"<p>{msg}</p></body></html>")
                _send_email("Your custom artwork is still waiting",
                            html, to=it["email"])
                mark_customization(it["email"], it.get("listing", ""),
                                   "recovered", recovered=True)
                sent += 1
            except Exception:  # noqa: BLE001
                pass
        results.append({"email": it["email"], "listing": it.get("listing", ""),
                        "message": msg})
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
