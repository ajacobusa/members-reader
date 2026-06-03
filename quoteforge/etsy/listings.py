import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_listing(quote: str, category: str, subcategory: str) -> dict:
    """Generate Etsy-optimized title, 13 tags, and description for a design."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"You are an expert Etsy SEO copywriter. Write a complete Etsy listing for a "
        f"print-on-demand wall art poster.\n\n"
        f"Quote on the design: \"{quote}\"\n"
        f"Category: {category} — {subcategory}\n\n"
        f"Provide exactly:\n"
        f"TITLE: [Under 140 characters, keyword-rich Etsy title]\n"
        f"TAGS: [13 tags separated by commas, each under 20 characters]\n"
        f"DESCRIPTION: [300+ word engaging Etsy description]\n\n"
        f"Output only in the format above. No extra text."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw: str = message.content[0].text
    listing: dict = {"title": "", "tags": [], "description": ""}
    for line in raw.strip().split("\n"):
        if line.startswith("TITLE:"):
            listing["title"] = line.replace("TITLE:", "").strip()
        elif line.startswith("TAGS:"):
            raw_tags = line.replace("TAGS:", "").strip()
            listing["tags"] = [t.strip() for t in raw_tags.split(",")][:13]
        elif line.startswith("DESCRIPTION:"):
            listing["description"] = line.replace("DESCRIPTION:", "").strip()
    return listing
