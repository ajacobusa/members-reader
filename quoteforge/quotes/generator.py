import re
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_quotes(category: str, subcategory: str, count: int = 5) -> list[str]:
    """Generate `count` original copyright-safe quotes via Claude API."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Write {count} original, memorable, copyright-safe motivational quotes "
        f"for the theme: {category} — specifically about {subcategory}.\n\n"
        f"Rules:\n"
        f"- Each quote must be 100% original — not from any song, movie, book, or celebrity\n"
        f"- Maximum 20 words per quote\n"
        f"- Emotionally resonant and professional\n"
        f"- Safe for print-on-demand wall art sold on Etsy\n"
        f"- One quote per line, no numbering, no quotation marks\n\n"
        f"Output only the quotes, nothing else."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw: str = message.content[0].text
    lines = raw.strip().split("\n")
    quotes = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip().strip('"').strip("'")
        if cleaned:
            quotes.append(cleaned)
    return quotes[:count]
