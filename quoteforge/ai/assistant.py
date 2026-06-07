"""Generic Claude text generation + AI gift notes / subscription emails.

Reuses the existing Claude client + cost tracking from quotes.generator, and is
fully TEST_MODE-safe: with no API key (or TEST_MODE on) it returns the provided
`mock` fallback so the whole app runs offline without spending money.
"""
from __future__ import annotations


def ai_text(prompt: str, operation: str, max_tokens: int = 400,
            mock: str = "") -> str:
    """Generate text with Claude. Returns `mock` in TEST_MODE / without a key."""
    from quoteforge.config import TEST_MODE, ANTHROPIC_API_KEY, CLAUDE_MODEL
    if TEST_MODE or not ANTHROPIC_API_KEY:
        return mock
    try:
        from quoteforge.quotes.generator import _client, _invoke
        msg = _invoke(_client(), operation=operation, model=CLAUDE_MODEL,
                      max_tokens=max_tokens,
                      messages=[{"role": "user", "content": prompt}])
        return "".join(getattr(b, "text", "") for b in msg.content).strip() or mock
    except Exception:  # noqa: BLE001 — never let AI break the flow
        return mock


def ai_vision_check(image_path) -> dict:
    """Optional Claude vision QC of a finished design. Returns
    {'ok': bool, 'note': str}. Safe: in TEST_MODE / no key / any error it returns
    ok=True (the deterministic preflight is the real gate; AI only adds a flag)."""
    from quoteforge.config import TEST_MODE, ANTHROPIC_API_KEY, CLAUDE_MODEL
    from pathlib import Path
    p = Path(image_path)
    if TEST_MODE or not ANTHROPIC_API_KEY or not p.exists():
        return {"ok": True, "note": "AI vision skipped"}
    try:
        import base64
        from quoteforge.quotes.generator import _client, _invoke
        ext = p.suffix.lower().lstrip(".")
        media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        msg = _invoke(
            _client(), operation="ai_vision_qc", model=CLAUDE_MODEL, max_tokens=200,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": media, "data": b64}},
                {"type": "text", "content": (
                    "You are a print-quality reviewer for personalized wall art. "
                    "Check for obvious defects: cut-off or overflowing text, "
                    "misspellings, blurriness, low contrast, or empty/broken design. "
                    "Reply with ONLY 'OK' if it looks good to send to the customer, "
                    "or 'ISSUE: <short reason>' if not.")}]}])
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        if text.upper().startswith("ISSUE"):
            return {"ok": False, "note": text}
        return {"ok": True, "note": text or "OK"}
    except Exception as exc:  # noqa: BLE001 — never block on AI failure
        return {"ok": True, "note": f"AI vision unavailable ({type(exc).__name__})"}


def gift_note(recipient: str, sender: str, occasion: str,
              buyer_message: str = "") -> str:
    """A warm, free personal gift-note card (Claude, with a graceful fallback)."""
    recipient = recipient or "you"
    sender = sender or "Someone who loves you"
    occ = (occasion or "this special moment").lower()
    fallback = (f"Dear {recipient},\n\nWishing you joy on {occ}. "
                f"May this little piece remind you how loved you are, today and "
                f"always.\n\nWith love,\n{sender}")
    if buyer_message:
        fallback = (f"Dear {recipient},\n\n{buyer_message}\n\nWith love,\n{sender}")
    prompt = (
        "Write a short, heartfelt gift-card note (45-70 words), warm and sincere, "
        "no clichés. It is a free note included with a personalized wall-art gift.\n"
        f"Recipient: {recipient}\nFrom: {sender}\nOccasion: {occasion}\n"
        + (f"Incorporate this sentiment from the sender: {buyer_message}\n"
           if buyer_message else "")
        + "Output only the note text (greeting, body, sign-off).")
    return ai_text(prompt, operation="gift_note", max_tokens=220, mock=fallback)


def subscription_renewal_email(name: str, plan: str, days_left: int,
                               shop: str) -> str:
    """A friendly subscription-ending reminder email body (Claude + fallback)."""
    name = name or "there"
    plan = plan or "subscription"
    when = ("today" if days_left <= 0 else f"in {days_left} day"
            + ("s" if days_left != 1 else ""))
    fallback = (
        f"Hi {name},\n\nYour {plan} with {shop} ends {when}. We'd love to keep "
        f"creating personalized art for the people you love. Renew anytime to keep "
        f"your benefits going - just reply to this email and we'll take care of it.\n\n"
        f"Thank you for being part of {shop}.")
    prompt = (
        f"Write a warm, concise subscription-renewal reminder email (70-110 words) "
        f"for {shop}, a personalized wall-art shop. Customer: {name}. Plan: {plan}. "
        f"It ends {when}. Encourage renewal, no pushy language, include a clear "
        f"call to renew. Output only the email body.")
    return ai_text(prompt, operation="subscription_email", max_tokens=260,
                   mock=fallback)
