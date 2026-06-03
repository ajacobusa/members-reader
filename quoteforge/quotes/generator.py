import re
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

# All supported output styles for custom personal messages
OUTPUT_STYLES = [
    "Custom Quote",
    "Personal Letter",
    "Poem",
    "Prayer",
    "Encouragement Letter",
    "Letter from Future Self",
]

# All relationship types for the personal message system
RELATIONSHIPS = [
    # Love
    "To My Wife", "To My Husband", "To My Girlfriend", "To My Boyfriend",
    "To My Fiancée", "To My Fiancé",
    # Family — children
    "To My Daughter", "To My Son",
    # Family — parents
    "To My Mom", "To My Dad", "To My Mother", "To My Father",
    # Grandparents
    "To My Grandmother", "To My Grandfather",
    "To My Granddaughter", "To My Grandson",
    # Siblings
    "To My Sister", "To My Brother",
    # Extended
    "To My Aunt", "To My Uncle",
    # Friendship
    "To My Best Friend", "To My Friend",
    # Professional / mentorship
    "To My Mentor", "To My Coach", "To My Teacher",
    # Self
    "To Myself", "Dear Future Me",
    # Faith
    "A Prayer For", "A Blessing For",
]

# Occasion types
OCCASIONS = [
    "Graduation", "Wedding", "Anniversary", "Birthday",
    "New Baby", "Baby Shower", "New Home", "New Job", "Promotion",
    "Retirement", "Christmas", "Mother's Day", "Father's Day",
    "Valentine's Day", "Just Because", "Memorial / In Memory Of",
    "Recovery & Healing", "Baptism", "Confirmation", "Dental School Graduation",
    "Medical School Graduation", "Nursing School Graduation",
]

# Scenery options for background matching
SCENERY_OPTIONS = [
    "Mountains", "Beach & Ocean", "Forest", "Sunrise", "Sunset",
    "Starry Night", "Wildflowers", "Lake & Reflection",
    "Desert Landscape", "Tropical", "Country Roads", "City Lights",
    "Soft Bokeh / Floral", "Abstract Watercolor", "Minimal & Clean",
]


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _clean_lines(raw: str, count: int) -> list[str]:
    lines = raw.strip().split("\n")
    quotes = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip().strip('"').strip("'")
        if cleaned:
            quotes.append(cleaned)
    return quotes[:count]


# ──────────────────────────────────────────────────────────────
# Standard quote generation (existing)
# ──────────────────────────────────────────────────────────────

def generate_quotes(category: str, subcategory: str, count: int = 5) -> list[str]:
    """Generate `count` original copyright-safe quotes via Claude API."""
    client = _client()
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


# ──────────────────────────────────────────────────────────────
# Personalized custom message generation (new core feature)
# ──────────────────────────────────────────────────────────────

def generate_personal_message(
    relationship: str,
    recipient_name: str,
    sender_name: str,
    occasion: str,
    memory_or_story: str,
    scenery: str,
    output_style: str,
    count: int = 3,
) -> list[str]:
    """Generate personalized poster text for a specific person, occasion, and relationship.

    Returns `count` variations separated by '---' in Claude's output,
    returned here as a list of strings (one per variation).

    output_style: one of OUTPUT_STYLES
    """
    client = _client()

    style_instructions = {
        "Custom Quote": (
            "Write a single short memorable quote (max 25 words) that captures this relationship and occasion. "
            "Format:\nLine 1: Recipient name + comma\nLine 2: The quote\nLine 3: 'With love, ' + sender name"
        ),
        "Personal Letter": (
            "Write a short heartfelt personal letter (4-6 sentences) as if from the sender to the recipient. "
            "Format:\nLine 1: Salutation (e.g. 'Dear Emma,')\n"
            "Lines 2-5: Letter body — warm, specific, emotionally resonant\n"
            "Line 6: Closing (e.g. 'With all my love, Mom')"
        ),
        "Poem": (
            "Write a short original poem (4-6 lines, rhyming or free verse) celebrating this relationship and occasion. "
            "Format:\nLine 1: Title (optional, short)\nLines 2+: Poem\nFinal line: 'For [Recipient], from [Sender]'"
        ),
        "Prayer": (
            "Write a short heartfelt prayer (4-5 sentences) for the recipient on this occasion. "
            "Format:\nLine 1: 'A Prayer for [Recipient Name]'\nLines 2-5: Prayer\nLine 6: 'Amen.' (if appropriate)"
        ),
        "Encouragement Letter": (
            "Write a short powerful encouragement letter (4-5 sentences) for the recipient on this milestone. "
            "Format:\nLine 1: Salutation\nLines 2-5: Encouragement — specific, bold, uplifting\nLine 6: Closing"
        ),
        "Letter from Future Self": (
            "Write a 'Letter from Future Self' — as if the recipient's future self is writing back to their present self. "
            "Format:\nLine 1: 'Dear [Recipient Name],'\n"
            "Lines 2-4: What their future self wants them to know (max 12 words each)\n"
            "Line 5: 'With love, Your Future Self'"
        ),
    }

    instructions = style_instructions.get(output_style, style_instructions["Personal Letter"])

    prompt = (
        f"Create {count} variations of a personalized wall art poster text.\n\n"
        f"Details:\n"
        f"  Relationship: {relationship}\n"
        f"  Recipient name: {recipient_name}\n"
        f"  Sender name: {sender_name}\n"
        f"  Occasion: {occasion}\n"
        f"  Special memory or story: {memory_or_story}\n"
        f"  Desired scenery/mood: {scenery}\n"
        f"  Output style: {output_style}\n\n"
        f"Style instructions:\n{instructions}\n\n"
        f"Rules:\n"
        f"- 100% original — not from any song, movie, book, or celebrity\n"
        f"- Deeply personal and emotionally resonant\n"
        f"- Safe for print-on-demand wall art sold on Etsy\n"
        f"- Weave in the memory/story naturally if provided\n"
        f"- Match the mood of the scenery: {scenery}\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the variations, nothing else."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]


# ──────────────────────────────────────────────────────────────
# Existing personalized modes
# ──────────────────────────────────────────────────────────────

def generate_life_chapter(name: str, age: int, goal: str, count: int = 3) -> list[str]:
    """Generate personalized 'Life Chapter' poster text."""
    client = _client()
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
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]


def generate_family_legacy(family_name: str, values: str, count: int = 3) -> list[str]:
    """Generate Family Legacy poster text."""
    client = _client()
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
    """Generate 'Letter to My Future Self' poster text."""
    client = _client()
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
