"""Phase 6: Order fulfillment workflow.

Processes an incoming Etsy order (customer personalization info)
and generates the custom message + Etsy-ready listing data instantly.
"""
import csv
from datetime import datetime
from pathlib import Path

import anthropic

from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, OUTPUT_DIR
from quoteforge.quotes.generator import generate_personal_message

# The Etsy personalization form text shown to customers in each listing.
# Copy this into the Etsy listing "Personalization" field.
ETSY_PERSONALIZATION_FORM = """\
Please provide the following details at checkout:

Recipient Name:
Your Name (sender):
Occasion: (e.g. Graduation, Birthday, Wedding, Just Because)
Relationship: (e.g. Daughter, Wife, Best Friend, Mom)
Favorite Scenery: (Mountains / Beach / Forest / Sunrise / Flowers / Starry Night / Minimal)
Message Tone: (Faith & Prayer / Inspirational / Emotional & Heartfelt / Celebratory)
Special Memory or Story (optional — the more you share, the more personal your print):

Note: Your personalized design will be delivered digitally within 24 hours of purchase.
"""

# Niche-specific Etsy listing titles (Phase 4 & 11)
NICHE_LISTING_TITLES: dict[str, list[str]] = {
    "Personalized Daughter Gifts": [
        "Personalized Daughter Gift | Custom Quote Print | Graduation Gift For Daughter",
        "To My Daughter Wall Art | Custom Inspirational Letter | Scenic Mountain Print",
        "Daughter Birthday Gift | Personalized Quote Poster | Gift From Mom Dad",
    ],
    "Personalized Son Gifts": [
        "Personalized Son Gift | Custom Encouragement Print | Graduation Gift For Son",
        "To My Son Wall Art | Custom Motivational Letter | Gift From Parents",
    ],
    "Christian Encouragement": [
        "Christian Wall Art | Faith Encouragement Print | Bible Inspired Quote Poster",
        "Christian Gift | Personalized Prayer Print | Faith Over Fear Wall Art",
        "Scripture Inspired Wall Art | Christian Nurse Gift | Faith Quote Print",
    ],
    "Graduation Gifts": [
        "Graduation Gift | Personalized Quote Print | Class of 2026 Wall Art",
        "Custom Graduation Message | Scenic Motivational Poster | Gift For Graduate",
        "Dental School Graduation Gift | Future DDS Wall Art | Medical School Gift",
    ],
    "Memorial Gifts": [
        "Memorial Gift | Personalized Remembrance Print | In Memory Wall Art",
        "Pet Memorial Print | Dog Rainbow Bridge | Custom Memorial Poster",
        "Sympathy Gift | Grief Healing Wall Art | Personalized Memorial Quote",
    ],
    "Future Dentist Gifts": [
        "Future Dentist Gift | Dental School Motivation | Pre-Dental Wall Art",
        "DAT Motivation Poster | Future DDS Print | Dental Student Gift",
        "Dental Hygienist Gift | Healthcare Worker Motivation | White Coat Gift",
    ],
    "Custom Love Letters": [
        "Custom Love Letter Print | To My Wife Gift | Personalized Anniversary Gift",
        "To My Husband Wall Art | Custom Wedding Anniversary Print | Love Quote Poster",
        "Personalized Wedding Gift | Custom Vow Print | To My Wife Anniversary",
    ],
    "Personalized Mom Gifts": [
        "Mother's Day Gift | Personalized Mom Print | Custom Quote From Daughter Son",
        "To My Mom Wall Art | Custom Heartfelt Letter | Best Mom Gift",
        "Grandmother Gift | Grandma Custom Quote Print | Gift From Grandchildren",
    ],
}

# Phase 11: Long-tail Etsy tags per niche (13 tags max, each ≤20 chars)
NICHE_TAGS: dict[str, list[str]] = {
    "Personalized Daughter Gifts": [
        "daughter gift", "graduation gift", "custom wall art", "daughter print",
        "mom to daughter", "personalized art", "mountain decor", "quote poster",
        "inspirational gift", "bedroom decor", "gift for her", "custom quote",
        "scenic wall art",
    ],
    "Christian Encouragement": [
        "christian gift", "faith wall art", "christian decor", "bible inspired",
        "faith quote print", "christian nurse", "scripture print", "prayer art",
        "faith over fear", "religious gift", "church decor", "christian mom",
        "spiritual gift",
    ],
    "Graduation Gifts": [
        "graduation gift", "class of 2026", "graduate gift", "custom quote",
        "motivational print", "college grad", "dental school", "medical school",
        "nursing grad", "law school gift", "achievement art", "milestone gift",
        "scenic poster",
    ],
    "Memorial Gifts": [
        "memorial gift", "sympathy gift", "remembrance print", "grief healing",
        "pet memorial", "rainbow bridge", "in memory of", "loss gift",
        "bereavement gift", "dog memorial", "cat memorial", "healing art",
        "custom memorial",
    ],
    "Custom Love Letters": [
        "anniversary gift", "wife gift", "husband gift", "love letter print",
        "wedding gift", "custom love art", "personalized vow", "romantic gift",
        "valentines day", "couples gift", "wedding decor", "love quote",
        "scenic love art",
    ],
}


def process_order(
    recipient_name: str,
    sender_name: str,
    relationship: str,
    occasion: str,
    scenery: str,
    tone: str,
    memory: str,
    output_style: str = "Personal Letter",
    variations: int = 3,
) -> dict:
    """Process an incoming Etsy order and generate the custom message.

    Returns a dict with:
      - variations: list of generated message strings
      - saved_paths: list of Path objects where files were saved
      - order_summary: human-readable summary for your records
    """
    results = generate_personal_message(
        relationship=relationship,
        recipient_name=recipient_name,
        sender_name=sender_name,
        occasion=occasion,
        memory_or_story=memory,
        scenery=scenery,
        output_style=output_style,
        count=variations,
    )

    # Save to output folder
    out_dir = OUTPUT_DIR / "Orders" / occasion / recipient_name
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for i, text in enumerate(results, 1):
        path = out_dir / f"variation_{i:02d}.txt"
        path.write_text(text, encoding="utf-8")
        saved_paths.append(path)

    # Append to order log CSV
    _log_order(
        recipient_name=recipient_name,
        sender_name=sender_name,
        relationship=relationship,
        occasion=occasion,
        scenery=scenery,
        output_style=output_style,
        saved_dir=str(out_dir),
    )

    return {
        "variations": results,
        "saved_paths": saved_paths,
        "order_summary": (
            f"Order: {relationship} | {occasion}\n"
            f"Recipient: {recipient_name} | From: {sender_name}\n"
            f"Style: {output_style} | Scenery: {scenery}\n"
            f"Saved to: {out_dir}"
        ),
    }


def _log_order(**kwargs: str) -> None:
    """Append order metadata to a running CSV log."""
    log_path = OUTPUT_DIR / "order_log.csv"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp", "recipient_name", "sender_name", "relationship",
        "occasion", "scenery", "output_style", "saved_dir",
    ]
    write_header = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({"timestamp": datetime.now().isoformat(), **kwargs})


def generate_post_purchase_email(
    recipient_name: str,
    occasion: str,
    sender_name: str,
    shop_name: str = "ScenicSoulPrints",
) -> str:
    """Generate a post-purchase follow-up email to build repeat customers."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Write a warm, professional post-purchase follow-up email from an Etsy shop.\n\n"
        f"Shop name: {shop_name}\n"
        f"Customer bought: A personalized {occasion} print for {recipient_name}\n"
        f"Sender of the gift: {sender_name}\n\n"
        f"The email should:\n"
        f"1. Thank them warmly for their purchase\n"
        f"2. Confirm their design is being created\n"
        f"3. Mention 3 related collections they might love:\n"
        f"   - Anniversary Collection\n"
        f"   - Family Legacy Collection\n"
        f"   - Future Self Collection\n"
        f"4. Invite them to leave a review\n"
        f"5. Be warm, personal, under 200 words\n\n"
        f"Output only the email body. No subject line needed."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
