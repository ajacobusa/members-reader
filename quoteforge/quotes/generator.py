import re
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def _clean_lines(raw: str, count: int) -> list[str]:
    lines = raw.strip().split("\n")
    quotes = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip().strip('"').strip("'")
        if cleaned:
            quotes.append(cleaned)
    return quotes[:count]


def generate_quotes(category: str, subcategory: str, count: int = 5) -> list[str]:
    """Generate `count` original copyright-safe quotes via Claude API."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
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
    return _clean_lines(message.content[0].text, count)


def generate_life_chapter(name: str, age: int, goal: str, count: int = 3) -> list[str]:
    """Generate personalized 'Life Chapter' poster text for a specific person.

    Returns lines formatted for a poster, e.g.:
      'Chapter 23: Becoming the Dentist'
      followed by supporting affirmation lines.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Create {count} variations of a personalized 'Life Chapter' poster for:\n"
        f"  Name: {name}\n"
        f"  Age: {age}\n"
        f"  Current goal / milestone: {goal}\n\n"
        f"Format each variation as exactly 3 lines:\n"
        f"Line 1: Chapter title — e.g. 'Chapter {age}: Becoming the [Role]'\n"
        f"Line 2: One short motivational sentence (max 12 words) specific to their journey\n"
        f"Line 3: One closing affirmation (max 10 words)\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the variations, nothing else. No numbering."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Return each variation as a single joined string (poster text block)
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]


def generate_family_legacy(family_name: str, values: str, count: int = 3) -> list[str]:
    """Generate Family Legacy poster text.

    Returns lines like:
      'The Johnson Family'
      'Faith. Service. Generosity.'
      + a supporting line
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Create {count} variations of a Family Legacy wall art poster for:\n"
        f"  Family name: {family_name}\n"
        f"  Core values or themes: {values}\n\n"
        f"Format each variation as exactly 3 lines:\n"
        f"Line 1: 'The {family_name} Family'\n"
        f"Line 2: Core values formatted as short phrases separated by periods (max 5 words total)\n"
        f"Line 3: One original family legacy sentence (max 15 words, heartfelt, print-on-demand safe)\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the variations, nothing else."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]


def generate_letter_to_future_self(context: str, count: int = 2) -> list[str]:
    """Generate 'Letter to My Future Self' poster text.

    context: brief description of the person's current journey
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Write {count} short 'Letter to My Future Self' poster texts for someone who is: {context}\n\n"
        f"Format each as:\n"
        f"Line 1: 'Dear Future Me,'\n"
        f"Lines 2-3: 2 short sentences (max 12 words each) of heartfelt encouragement\n"
        f"Line 4: A short closing (max 8 words)\n\n"
        f"Separate each with '---'\n"
        f"Original, print-on-demand safe, emotionally resonant. Output only the letters."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]
