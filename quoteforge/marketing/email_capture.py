"""Email-capture kit — build an audience you own.

Generates everything needed to start a mailing list around the shop:
  * a QR code PNG pointing at your signup URL (for package inserts / business
    cards) - uses the `qrcode` lib if installed, else falls back to a hosted QR
    image URL and prints an install hint;
  * Etsy shop-announcement copy with a signup CTA;
  * Linktree block suggestions;
  * a drop-in website signup HTML snippet;
  * a printable "thank-you insert" card copy with the QR.

No hard dependency: works without `qrcode` (graceful fallback).
"""
from __future__ import annotations

import urllib.parse
from pathlib import Path


def make_qr(url: str, out: Path, box: int = 10) -> tuple[Path | None, str]:
    """Write a QR PNG for `url`. Returns (path or None, status message)."""
    if not url:
        return None, "no SIGNUP_URL set - skipping QR"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        import qrcode  # optional dependency
        img = qrcode.make(url, box_size=box)
        img.save(out)
        return out, f"QR saved -> {out}"
    except ImportError:
        # Fallback: a hosted QR (also written as a tiny .txt with the URL so the
        # operator can paste it into any QR generator).
        api = ("https://api.qrserver.com/v1/create-qr-code/?size=400x400&data="
               + urllib.parse.quote(url))
        out.with_suffix(".qr-url.txt").write_text(api, encoding="utf-8")
        return None, ("qrcode lib not installed - wrote a hosted-QR URL instead "
                      f"({out.with_suffix('.qr-url.txt')}). "
                      "Install with: pip install qrcode[pil]")


def announcement_copy(shop: str, signup_url: str) -> str:
    return (
        f"Welcome to {shop}! Every piece is personalized to order - a name, a "
        f"date, your own words - with a free digital proof before anything "
        f"prints.\n\n"
        f"Join our list for early access to new designs + a welcome discount: "
        f"{signup_url or '[YOUR SIGNUP LINK]'}"
    )


def linktree_blocks(shop: str, shop_url: str, signup_url: str) -> list[str]:
    return [
        f"🛍  Shop {shop} on Etsy  ->  {shop_url}",
        f"💌  Join the list (early access + welcome offer)  ->  {signup_url or '[SIGNUP]'}",
        "📌  Follow us on Pinterest for gift ideas  ->  [PINTEREST]",
        "⭐  Read reviews & see customer photos  ->  [ETSY REVIEWS]",
    ]


def signup_html_snippet(signup_url: str) -> str:
    action = signup_url or "[YOUR_FORM_ACTION_URL]"
    return (
        '<form class="jf-signup" action="' + action + '" method="post">\n'
        '  <h3>Get early access + a welcome offer</h3>\n'
        '  <input type="email" name="email" placeholder="you@email.com" required>\n'
        '  <button type="submit">Join the list</button>\n'
        '  <p style="font-size:12px;color:#888">No spam. Unsubscribe anytime.</p>\n'
        '</form>'
    )


def insert_card_copy(shop: str, signup_url: str) -> str:
    return (
        f"Thank you for your order from {shop}!\n\n"
        "We hope your personalized piece brings a little more meaning to your "
        "space. Two small favors:\n"
        "  1) A review with a photo helps our small shop enormously.\n"
        "  2) Scan the QR to join our list for early access + a welcome offer.\n\n"
        f"   {signup_url or '[SIGNUP LINK]'}\n"
    )


def build_capture_kit(out_dir=None) -> dict:
    """Write the full kit to disk. Returns a summary dict."""
    from quoteforge.config import OUTPUT_DIR, SHOP_NAME, SIGNUP_URL
    try:
        from quoteforge.config import ETSY_SHOP_URL
    except Exception:  # noqa: BLE001
        ETSY_SHOP_URL = ""
    shop_url = ETSY_SHOP_URL or f"https://www.etsy.com/shop/{SHOP_NAME}"

    out = Path(out_dir) if out_dir else (OUTPUT_DIR / "email_capture")
    out.mkdir(parents=True, exist_ok=True)

    qr_path, qr_status = make_qr(SIGNUP_URL, out / "signup_qr.png")
    (out / "shop_announcement.txt").write_text(
        announcement_copy(SHOP_NAME, SIGNUP_URL), encoding="utf-8")
    (out / "linktree.txt").write_text(
        "\n".join(linktree_blocks(SHOP_NAME, shop_url, SIGNUP_URL)), encoding="utf-8")
    (out / "signup_snippet.html").write_text(
        signup_html_snippet(SIGNUP_URL), encoding="utf-8")
    (out / "thankyou_insert.txt").write_text(
        insert_card_copy(SHOP_NAME, SIGNUP_URL), encoding="utf-8")

    return {
        "dir": str(out),
        "qr": str(qr_path) if qr_path else None,
        "qr_status": qr_status,
        "signup_url": SIGNUP_URL,
        "files": ["shop_announcement.txt", "linktree.txt",
                  "signup_snippet.html", "thankyou_insert.txt"],
    }
