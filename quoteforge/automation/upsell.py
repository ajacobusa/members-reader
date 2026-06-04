"""Upsell and review automation.

After purchase: offer canvas/framed upgrade within 2 hours.
After delivery: request review after 14 days.
"""
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, PIPELINE_REVIEW_DELAY_DAYS


def generate_upsell_message(
    customer_name: str,
    occasion: str,
    original_product: str = "poster",
    shop_name: str = "ScenicSoulPrints",
) -> dict[str, str]:
    """Generate upsell offers for canvas and framed upgrades.

    Returns dict: {canvas_message, framed_message, bundle_message}
    """
    if not ANTHROPIC_API_KEY:
        return {
            "canvas_message": _base_canvas_upsell(customer_name, shop_name),
            "framed_message": _base_framed_upsell(customer_name, shop_name),
            "bundle_message": _base_bundle_upsell(customer_name, shop_name),
        }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Write 3 short Etsy upsell messages for a customer who just ordered a personalized "
        f"{original_product} for {occasion}.\n\n"
        f"Customer name: {customer_name}\n"
        f"Shop: {shop_name}\n\n"
        f"Write:\n"
        f"CANVAS: Short message offering the canvas upgrade (~$15 more than poster)\n"
        f"FRAMED: Short message offering the framed print upgrade (~$25 more)\n"
        f"BUNDLE: Short message offering a 3-print matching set at a discount\n\n"
        f"Each under 60 words. Warm, not pushy. No emojis. Output only the 3 messages labeled CANVAS:, FRAMED:, BUNDLE:"
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    result = {"canvas_message": "", "framed_message": "", "bundle_message": ""}
    for line in raw.split("\n"):
        if line.startswith("CANVAS:"):
            result["canvas_message"] = line.replace("CANVAS:", "").strip()
        elif line.startswith("FRAMED:"):
            result["framed_message"] = line.replace("FRAMED:", "").strip()
        elif line.startswith("BUNDLE:"):
            result["bundle_message"] = line.replace("BUNDLE:", "").strip()
    # fill blanks with base versions
    if not result["canvas_message"]:
        result["canvas_message"] = _base_canvas_upsell(customer_name, shop_name)
    if not result["framed_message"]:
        result["framed_message"] = _base_framed_upsell(customer_name, shop_name)
    if not result["bundle_message"]:
        result["bundle_message"] = _base_bundle_upsell(customer_name, shop_name)
    return result


def _base_canvas_upsell(name: str, shop: str) -> str:
    return (f"Hi {name}! I noticed you ordered a poster — did you know I also offer "
            f"this design on canvas? Canvas prints have a stunning gallery-wrapped finish "
            f"and make a truly special gift. Message me if you'd like to upgrade!")


def _base_framed_upsell(name: str, shop: str) -> str:
    return (f"Hi {name}! Your personalized print is being created. "
            f"If you'd like it to arrive ready to hang, I offer a beautifully framed version. "
            f"Just reply here and I can swap your order!")


def _base_bundle_upsell(name: str, shop: str) -> str:
    return (f"Hi {name}! Many customers love ordering a matching 3-print set — "
            f"one for the recipient, one to keep, and one as a gift. "
            f"I offer a 15% discount on sets of 3. Interested?")


def generate_review_request(
    customer_name: str,
    occasion: str,
    recipient_name: str,
    shop_name: str = "ScenicSoulPrints",
    days_since_delivery: int = 14,
) -> str:
    """Generate a personalized review request message."""
    if not ANTHROPIC_API_KEY:
        return _base_review_request(customer_name, recipient_name, shop_name)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Write a warm, personal Etsy review request message.\n\n"
        f"Customer: {customer_name}\n"
        f"They ordered a personalized {occasion} print for: {recipient_name}\n"
        f"It was delivered {days_since_delivery} days ago\n"
        f"Shop: {shop_name}\n\n"
        f"Rules:\n"
        f"- Under 80 words\n"
        f"- Warm, genuine, not corporate\n"
        f"- Reference the specific occasion\n"
        f"- No emojis\n"
        f"- End with a specific ask for a review\n\n"
        f"Output only the message."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _base_review_request(name: str, recipient: str, shop: str) -> str:
    return (
        f"Hi {name}! I hope your personalized print arrived safely and that {recipient} "
        f"loved it. If you have a moment, I would be so grateful if you could leave a review "
        f"on my Etsy shop. It means the world to a small business like mine and helps other "
        f"customers find me. Thank you so much!"
    )


def should_send_review(order_created_at: str, delivery_days: int = 7) -> bool:
    """Returns True if it's time to send the review request."""
    from datetime import datetime
    try:
        created = datetime.fromisoformat(order_created_at)
        days_elapsed = (datetime.now() - created).days
        return days_elapsed >= (delivery_days + PIPELINE_REVIEW_DELAY_DAYS)
    except Exception:
        return False
