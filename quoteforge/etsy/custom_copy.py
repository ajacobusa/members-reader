"""Ready-to-paste Etsy listing copy for buyer-supplied quotes and photos.

Centralises the customer-facing wording so it matches what the pipeline actually
enforces (verbatim custom text, the photo-quality gate, the proof step). Use
`admin custom-copy` to print it, then paste the relevant blocks into the listing
description / personalization instructions / FAQ.
"""

# Personalization-box instructions (Etsy limits this field, keep it tight).
PERSONALIZATION_INSTRUCTIONS = """\
Please enter:
- Recipient's name
- Occasion (e.g. graduation, birthday, memorial)
- Relationship (e.g. daughter, mom, husband)
- A short story or memory (optional - helps us personalize)
- YOUR OWN QUOTE (optional): type your exact wording here and we'll use it
  word-for-word. Leave blank and we'll craft a personalized message for you.
"""

# A short block for the listing description body.
DESCRIPTION_BLOCK = """\
MAKE IT YOURS
- Your own words: prefer your exact wording? Type it in the personalization box
  and we'll print it exactly as written.
- Add a photo (select the photo option): after ordering, send us your photo via
  Etsy Messages and we'll create your proof.
- Free digital proof: nothing prints until you approve it.
"""

# The photo-requirements block — must match the pipeline's quality gate.
PHOTO_REQUIREMENTS = """\
PHOTO GIFTS - PLEASE READ
For the sharpest print, your photo needs to be high resolution:
- Send the ORIGINAL, full-size photo - not a screenshot or a copy saved from
  social media (those are compressed and print blurry).
- On a phone, choose "Actual Size" or "Large" when sharing/emailing.
- Recommended minimums:
    8x10   ->  about 1500 x 1875 px
    11x14  ->  about 2100 x 2700 px
    16x20  ->  about 3000 x 3750 px
    18x24  ->  about 3300 x 4200 px
If a photo is too low-resolution to print well, we'll message you right away and
ask for a better version before printing - we never print a blurry photo.
"""

# A one-line FAQ pair.
FAQ = [
    ("Can I use my own quote or wording?",
     "Yes! Type your exact words in the personalization box and we'll print them "
     "word-for-word. Leave it blank and we'll craft a personalized message."),
    ("Can I add my own photo?",
     "Yes. Choose the photo option, then send your photo via Etsy Messages after "
     "ordering. Please send the original full-size image so it prints sharply - "
     "if it's too low-resolution we'll ask for a better one before printing."),
    ("Will I see it before it prints?",
     "Always. We send a free digital proof for your approval - nothing is printed "
     "until you're happy."),
]


def format_custom_copy() -> str:
    lines = ["=" * 64, "JOFFIELS - CUSTOM QUOTE / PHOTO LISTING COPY", "=" * 64,
             "\n## PERSONALIZATION BOX INSTRUCTIONS\n", PERSONALIZATION_INSTRUCTIONS,
             "\n## DESCRIPTION BLOCK (add to listing body)\n", DESCRIPTION_BLOCK,
             "\n## PHOTO REQUIREMENTS (add for photo products)\n", PHOTO_REQUIREMENTS,
             "\n## FAQ\n"]
    for q, a in FAQ:
        lines.append(f"Q: {q}\nA: {a}\n")
    lines.append("=" * 64)
    return "\n".join(lines)
