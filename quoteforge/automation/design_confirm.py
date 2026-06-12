"""Design save + accept + customer confirmation email.

When the customer accepts their final proof on the storefront, we record the
acceptance against their saved design and email them a confirmation of exactly
what they approved (AI-personalized when available, deterministic otherwise).
This is a design/intent confirmation - the purchase itself completes on Etsy and
a separate free proof is still sent before printing.
"""
from __future__ import annotations


def _email_body(email: str, summary: str) -> str:
    """Confirmation email body - AI-personalized when available, template otherwise."""
    try:
        from quoteforge.ai.assistant import ai_text
        txt = ai_text(
            "Write a short, warm confirmation email body (3-4 sentences, no subject) "
            "to a customer who just approved their personalized wall-art design. "
            "Thank them, confirm we've saved their layout, and reassure them a free "
            "digital proof will be sent before anything is printed. Do not invent "
            f"prices or dates. Their order:\n{summary}", "design_confirmation",
            max_tokens=200)
        if txt and txt.strip():
            return txt.strip()
    except Exception:  # noqa: BLE001
        pass
    return ("Thank you - we've saved your approved design! Here's what you confirmed:\n\n"
            f"{summary}\n\n"
            "We'll prepare a FREE digital proof and send it to you before anything is "
            "printed, so you can give the final go-ahead. If you'd like to change the "
            "wording, photo, frame or layout, just reply to this email.")


def confirm_design(email: str, summary: str = "", design_json: str = "",
                   design_id: str = "default", send: bool = True) -> dict:
    """Save the accepted design and (optionally) email the customer a confirmation."""
    from quoteforge.db.database import init_db, save_design, accept_design
    init_db()
    email = (email or "").strip().lower()
    if "@" not in email:
        return {"ok": False, "error": "valid email required", "emailed": False}
    save_design(email, design_json=design_json, design_id=design_id, summary=summary)
    accept_design(email, design_id)
    emailed = False
    if send:
        try:
            from quoteforge.automation.emailer import _send_email
            body = _email_body(email, summary or "(your personalized design)")
            html = ("<html><body style='font-family:Arial'>"
                    f"<p>{body.replace(chr(10), '<br>')}</p></body></html>")
            _send_email("Your Joffiels design is confirmed", html, to=email)
            emailed = True
        except Exception:  # noqa: BLE001
            emailed = False
    return {"ok": True, "emailed": emailed}
