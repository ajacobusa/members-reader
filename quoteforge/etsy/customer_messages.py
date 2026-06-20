"""Customer communication templates from Customer_Message_Templates.docx.

Four Etsy message types, each with:
- A base template (quick copy-paste)
- An AI-personalized version (Claude adds name, occasion, warmth)
"""
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

# ── Base templates (direct from Customer_Message_Templates.docx) ─
BASE_TEMPLATES: dict[str, str] = {
    "Order Received": (
        "Thank you for your order! Your design is confirmed exactly as you "
        "approved it on screen, and it is heading into production now. "
        "Please feel free to message me if you have any questions!"
    ),
    "Proof Ready": (
        "Here is a copy of your approved proof for your records - this is "
        "exactly what we are printing, just as you approved it on screen. "
        "No action needed; your order is already on its way to production. Thank you!"
    ),
    "In Production": (
        "Great news! Your personalized design has been approved and sent to production. "
        "Our print partner is now carefully making your item. "
        "I will share tracking details the moment it ships. Thank you for your patience!"
    ),
    "Order Shipped": (
        "Great news! Your order has shipped and is on its way. "
        "You will receive a tracking number shortly so you can follow it to your door. "
        "Thank you for choosing my shop — I hope your personalized item brings joy every time you see it!"
    ),
    "Review Request": (
        "Thank you for your purchase! I hope your personalized item arrived safely "
        "and that you and your recipient love it. "
        "If you enjoyed your experience, I would greatly appreciate a review — "
        "it helps my small shop grow and helps other customers find me. Thank you so much!"
    ),
}

# ── Tone options for AI personalization ─────────────────────────
MESSAGE_TONES = [
    "Warm & Professional",
    "Friendly & Casual",
    "Formal & Polished",
    "Faith-Based & Warm",
    "Enthusiastic & Celebratory",
]

MESSAGE_TYPES = list(BASE_TEMPLATES.keys())


def get_base_template(message_type: str) -> str:
    """Return the base template text for a given message type."""
    return BASE_TEMPLATES.get(message_type, "")


def generate_personalized_customer_message(
    message_type: str,
    customer_name: str,
    occasion: str,
    recipient_name: str,
    shop_name: str = "ScenicSoulPrints",
    tone: str = "Warm & Professional",
) -> str:
    """Generate an AI-personalized version of an Etsy customer message.

    Takes the base template and enriches it with customer-specific details.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")

    base = BASE_TEMPLATES.get(message_type, "")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = (
        f"Rewrite this Etsy shop message to feel personal and warm for this specific customer.\n\n"
        f"Base message:\n{base}\n\n"
        f"Personalization details:\n"
        f"  Customer name: {customer_name}\n"
        f"  Occasion (what they ordered): {occasion}\n"
        f"  Recipient of the gift: {recipient_name}\n"
        f"  Shop name: {shop_name}\n"
        f"  Desired tone: {tone}\n\n"
        f"Rules:\n"
        f"- Address the customer by first name at the start\n"
        f"- Reference their specific occasion naturally (e.g. 'your daughter's graduation')\n"
        f"- Keep it under 100 words — concise and warm\n"
        f"- Do NOT use emojis\n"
        f"- Sound like a real person running a small shop, not a corporation\n\n"
        f"Output only the message text, nothing else."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def get_all_base_templates_formatted() -> str:
    """Return all 4 base templates as a formatted copyable block."""
    lines = []
    for msg_type, text in BASE_TEMPLATES.items():
        lines.append(f"── {msg_type} ──")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)
