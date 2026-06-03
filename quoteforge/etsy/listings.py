import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_listing(quote: str, category: str, subcategory: str) -> dict:
    """Generate Etsy-optimized title, 13 tags, and description for a design."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set. Open quoteforge/config.py and add your key.")
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
    lines = raw.strip().split("\n")
    desc_lines: list[str] = []
    in_description = False
    for line in lines:
        if line.startswith("TITLE:"):
            listing["title"] = line.replace("TITLE:", "").strip()
            in_description = False
        elif line.startswith("TAGS:"):
            raw_tags = line.replace("TAGS:", "").strip()
            listing["tags"] = [t.strip() for t in raw_tags.split(",")][:13]
            in_description = False
        elif line.startswith("DESCRIPTION:"):
            desc_lines.append(line.replace("DESCRIPTION:", "").strip())
            in_description = True
        elif in_description:
            desc_lines.append(line)
    listing["description"] = " ".join(desc_lines).strip()
    return listing
