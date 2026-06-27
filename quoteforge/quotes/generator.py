"""Claude-powered personal message generator with a TEST_MODE mock fallback."""
import re
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, TEST_MODE


def _mock_personal_message(recipient_name: str, sender_name: str,
                           occasion: str, output_style: str,
                           count: int) -> list[str]:
    """Deterministic mock output for TEST_MODE / no-API-key runs.

    Lets the full pipeline be exercised end-to-end without spending money
    or requiring credentials. Clearly marked so it never reaches a customer.
    """
    name = recipient_name or "Friend"
    sender = sender_name or "Someone who loves you"
    base = (
        f"Dear {name},\n"
        f"On this {occasion}, know how proud we are of you. "
        f"Your strength, your heart, and your journey inspire everyone around you. "
        f"Keep reaching for everything you dream of.\n"
        f"With love, {sender}"
    )
    return [f"[TEST MODE - {output_style}] {base}" for _ in range(max(1, count))]

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
    # Family - children
    "To My Daughter", "To My Son",
    # Family - parents
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

# Occasion types - comprehensive, year-round coverage. The complete taxonomy
# (calendar months, religions, milestones, emotional events) lives in
# quoteforge.etsy.occasions; this is the de-duplicated flat list the GUI uses.
def _build_occasions() -> list[str]:
    """The occasion choices offered to buyers (base list + extras)."""
    base = [
        "Graduation", "Wedding", "Anniversary", "Birthday",
        "New Baby", "Baby Shower", "New Home", "New Job", "Promotion",
        "Retirement", "Christmas", "Mother's Day", "Father's Day",
        "Valentine's Day", "Just Because", "Memorial / In Memory Of",
        "Recovery & Healing", "Baptism", "Confirmation",
    ]
    try:
        from quoteforge.etsy.occasions import all_occasions
        merged = list(dict.fromkeys(base + all_occasions()))  # dedupe, keep order
        return merged
    except Exception:
        return base


OCCASIONS = _build_occasions()

# Scenery options for background matching
SCENERY_OPTIONS = [
    "Mountains", "Beach & Ocean", "Forest", "Sunrise", "Sunset",
    "Starry Night", "Wildflowers", "Lake & Reflection",
    "Desert Landscape", "Tropical", "Country Roads", "City Lights",
    "Soft Bokeh / Floral", "Abstract Watercolor", "Minimal & Clean",
]


def _client() -> anthropic.Anthropic:
    """An Anthropic API client (raises when no API key is configured)."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _invoke(client, operation: str = "quote_generation", **kwargs):
    """Call Claude and record the token cost of every request. Best-effort —
    cost logging never breaks generation."""
    message = client.messages.create(**kwargs)
    try:
        from quoteforge.automation.cost_tracker import record_anthropic_usage
        record_anthropic_usage(kwargs.get("model", CLAUDE_MODEL),
                               getattr(message, "usage", None),
                               operation=operation)
    except Exception:  # noqa: BLE001
        pass
    return message


def _clean_lines(raw: str, count: int) -> list[str]:
    """Split the model's raw output into exactly ``count`` clean quote lines.
    Drops empty lines and any line containing profanity (safety net over the
    prompt-level rules). No min-length here - short quotes are legitimate."""
    from quoteforge.quotes.moderation import is_clean
    lines = raw.strip().split("\n")
    quotes = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip().strip('"').strip("'")
        if cleaned and is_clean(cleaned):
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
        f"for the theme: {category} - specifically about {subcategory}.\n\n"
        f"Rules:\n"
        f"- Each quote must be 100% original - not from any song, movie, book, or celebrity\n"
        f"- Maximum 20 words per quote\n"
        f"- Emotionally resonant and professional\n"
        f"- Safe for print-on-demand wall art sold on Etsy\n"
        f"- One quote per line, no numbering, no quotation marks\n\n"
        f"Output only the quotes, nothing else."
    )
    message = _invoke(client,
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
    force_real: bool = False,
) -> list[str]:
    """Generate personalized poster text for a specific person, occasion, and relationship.

    Returns `count` variations separated by '---' in Claude's output,
    returned here as a list of strings (one per variation).

    output_style: one of OUTPUT_STYLES
    force_real: bypass the TEST_MODE mock and call the real Claude API. Use this
        to verify real AI quality during the sample flow WITHOUT disabling the
        global TEST_MODE flag (which would also arm live Gelato fulfillment).
        Requires ANTHROPIC_API_KEY.
    """
    # TEST_MODE / no key → return realistic mock so the pipeline runs end-to-end.
    # force_real overrides this so the sample flow can preview true AI output.
    if not force_real and (TEST_MODE or not ANTHROPIC_API_KEY):
        return _mock_personal_message(
            recipient_name, sender_name, occasion, output_style, count)

    client = _client()  # raises a clear error if ANTHROPIC_API_KEY is missing

    style_instructions = {
        "Custom Quote": (
            "Write a single short memorable quote (max 25 words) that captures this relationship and occasion. "
            "Format:\nLine 1: Recipient name + comma\nLine 2: The quote\nLine 3: 'With love, ' + sender name"
        ),
        "Personal Letter": (
            "Write a short heartfelt personal letter (4-6 sentences) as if from the sender to the recipient. "
            "Format:\nLine 1: Salutation (e.g. 'Dear Emma,')\n"
            "Lines 2-5: Letter body - warm, specific, emotionally resonant\n"
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
            "Format:\nLine 1: Salutation\nLines 2-5: Encouragement - specific, bold, uplifting\nLine 6: Closing"
        ),
        "Letter from Future Self": (
            "Write a 'Letter from Future Self' - as if the recipient's future self is writing back to their present self. "
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
        f"- 100% original - not from any song, movie, book, or celebrity\n"
        f"- Deeply personal and emotionally resonant\n"
        f"- Safe for print-on-demand wall art sold on Etsy\n"
        f"- Weave in the memory/story naturally if provided\n"
        f"- Match the mood of the scenery: {scenery}\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the variations, nothing else."
    )
    try:
        message = _invoke(client,
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
    except Exception:  # noqa: BLE001 - a live API error must never hard-crash the
        # caller; degrade to the deterministic mock instead of raising.
        return _mock_personal_message(
            recipient_name, sender_name, occasion, output_style, count)
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    # Safety net over the prompt rules: drop profane / too-short (truncated)
    # variations. If everything is filtered out, fall back to the safe mock rather
    # than handing the customer empty or unusable text.
    from quoteforge.quotes.moderation import filter_variations
    variations = filter_variations(variations)
    if not variations:
        return _mock_personal_message(
            recipient_name, sender_name, occasion, output_style, count)
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
        f"Line 1: Chapter title - e.g. 'Chapter {age}: Becoming the [Role]'\n"
        f"Line 2: One short motivational sentence (max 12 words) specific to their journey\n"
        f"Line 3: One closing affirmation (max 10 words)\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the variations, nothing else. No numbering."
    )
    message = _invoke(client,
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
    message = _invoke(client,
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]


# ──────────────────────────────────────────────────────────────
# Prompt-template generators (from ChatGPT_Quote_Prompts.txt)
# ──────────────────────────────────────────────────────────────

def generate_heartfelt_message(
    recipient: str,
    occasion: str,
    relationship: str,
    tone: str,
    word_count: int = 120,
    count: int = 3,
) -> list[str]:
    """Prompt template 1: Heartfelt personalized message.

    Matches the ChatGPT_Quote_Prompts.txt template exactly, using Claude.
    """
    client = _client()
    prompt = (
        f"Create {count} variations of a heartfelt personalized message.\n\n"
        f"Recipient: {recipient}\n"
        f"Occasion: {occasion}\n"
        f"Relationship: {relationship}\n"
        f"Tone: {tone}\n"
        f"Length: approximately {word_count} words\n\n"
        f"Rules:\n"
        f"- Avoid clichés - make it emotionally meaningful and specific\n"
        f"- 100% original - safe for print-on-demand wall art\n"
        f"- Each variation should feel distinct in structure or angle\n"
        f"- Address the recipient by name\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the messages, nothing else."
    )
    message = _invoke(client,
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    return [v.strip() for v in raw.split("---") if v.strip()][:count]


def generate_christian_encouragement(
    recipient: str,
    challenge: str,
    bible_theme: str,
    count: int = 3,
) -> list[str]:
    """Prompt template 2: Christian encouragement letter.

    Matches the ChatGPT_Quote_Prompts.txt template exactly.
    """
    client = _client()
    prompt = (
        f"Create {count} variations of a Christian encouragement letter.\n\n"
        f"Recipient: {recipient}\n"
        f"Challenge they are facing: {challenge}\n"
        f"Favorite Bible theme: {bible_theme}\n\n"
        f"Rules:\n"
        f"- Deeply faith-based, warm, and uplifting\n"
        f"- Weave the Bible theme naturally - do not copy exact Bible verses (paraphrase in your own words)\n"
        f"- Speak directly to the challenge with hope\n"
        f"- 100% original - safe for print-on-demand wall art\n"
        f"- Address the recipient by name\n"
        f"- 100-150 words per variation\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the letters, nothing else."
    )
    message = _invoke(client,
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    return [v.strip() for v in raw.split("---") if v.strip()][:count]


def generate_graduation_message(
    name: str,
    degree: str,
    career_goal: str,
    count: int = 3,
) -> list[str]:
    """Prompt template 3: Graduation personalized message.

    Matches the ChatGPT_Quote_Prompts.txt template exactly.
    """
    client = _client()
    prompt = (
        f"Create {count} variations of a personalized graduation message.\n\n"
        f"Name: {name}\n"
        f"Degree: {degree}\n"
        f"Career Goal: {career_goal}\n\n"
        f"Rules:\n"
        f"- Specific to their degree and career goal - not generic\n"
        f"- Bold, celebratory, and forward-looking\n"
        f"- 100% original - safe for print-on-demand wall art\n"
        f"- Address the graduate by name\n"
        f"- 80-120 words per variation\n\n"
        f"Separate each variation with '---'\n"
        f"Output only the messages, nothing else."
    )
    message = _invoke(client,
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    return [v.strip() for v in raw.split("---") if v.strip()][:count]


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
    message = _invoke(client,
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    variations = [v.strip() for v in raw.split("---") if v.strip()]
    return variations[:count]
