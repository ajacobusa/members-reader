"""AI Gift Finder - recommend a product/frame/colors/quote from a short quiz.

Deterministic recommendation engine (works offline, no API): maps the buyer's
answers (recipient, occasion, relationship, budget, style) to a specific
material, frame, color palette, and the best-matching listing. A JS mirror runs
the same logic on the site so the quiz works client-side.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Quiz options (value, label).
OCCASIONS = ["Birthday", "Anniversary", "Wedding", "Mother's Day", "Father's Day",
             "Valentine's Day", "Graduation", "New Baby", "Housewarming",
             "Christmas", "Just because"]
RELATIONSHIPS = ["Daughter", "Son", "Mom", "Dad", "Wife", "Husband", "Grandma",
                 "Best Friend", "Family", "Pet"]
BUDGETS = [("under50", "Under $50", "poster"),
           ("50to100", "$50-$100", "framed"),
           ("100plus", "$100+", "acrylic")]
# Each style's PREFERRED frame is aspirational; _sellable_frame() maps it to a
# frame the shop can actually fulfil (re-audit 2026-07-21, finding F3: 4 of 5
# styles recommended finishes a buyer couldn't find at checkout - a dead-end).
_STYLE_SEEDS = [("classic", "Classic", "Premium Solid Oak", ["#0f3d2e", "#f4efe6"]),
                ("modern", "Modern", "Classic Black Wood", ["#1b1b1f", "#ffffff"]),
                ("elegant", "Elegant", "Gallery Gold", ["#2e3a55", "#c9a84c"]),
                ("minimal", "Minimal", "Classic White Wood", ["#f4efe6", "#1b1b1f"]),
                ("warm", "Warm", "Premium Walnut", ["#3a2e24", "#e8d8a8"])]


def _sellable_frame(preferred: str) -> str:
    """The preferred finish when it is fulfillable, else the closest frame the
    shop actually sells (never a finish the picker can't offer)."""
    try:
        from quoteforge.etsy.frames import available_frames
        names = [f.name for f in available_frames()]
    except Exception:  # noqa: BLE001 - fall back to the preference
        return preferred
    if not names:
        return ""
    return preferred if preferred in names else names[0]


STYLES = [(sid, label, _sellable_frame(frame), palette)
          for sid, label, frame, palette in _STYLE_SEEDS]


def _material_for_budget(budget: str) -> str:
    """Map a budget bracket to the recommended product material."""
    return {"under50": "Poster", "50to100": "Framed", "100plus": "Acrylic"}.get(
        budget, "Framed")


def recommend(occasion: str = "", relationship: str = "", budget: str = "",
              style: str = "") -> dict:
    """Return a recommendation: material, frame, palette, quote angle, and the
    best-matching listing number (from the 20 launch listings)."""
    st = next((s for s in STYLES if s[0] == style), STYLES[0])
    material = _material_for_budget(budget)
    frame = st[2] if material == "Framed" else ""
    palette = st[3]

    # Best-matching listing: score launch listings by relationship + occasion.
    best_n, best_score = 1, -1
    try:
        from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
        for l in LAUNCH_PACK_20:
            score = 0
            if relationship and relationship.lower() in (l.relationship or "").lower():
                score += 2
            if occasion and occasion.lower() in (l.occasion or "").lower():
                score += 2
            if score > best_score:
                best_score, best_n = score, l.n
    except Exception as exc:  # noqa: BLE001 - scoring is best-effort, falls back
        logger.debug("gift-finder listing scoring skipped: %s", exc)

    quote_angle = (f"A heartfelt {occasion or 'gift'} message for your "
                   f"{relationship or 'loved one'}, in your own words.")
    return {
        "material": material, "frame": frame, "palette": palette,
        "listing_n": best_n, "style": st[1], "quote_angle": quote_angle,
        "headline": f"Perfect: a {st[1].lower()} {material.lower()} for your "
                    f"{(relationship or 'loved one').lower()}'s "
                    f"{(occasion or 'special day').lower()}",
    }


def quiz_config() -> dict:
    """Compact config for the on-page quiz (client-side mirror)."""
    return {
        "occasions": OCCASIONS,
        "relationships": RELATIONSHIPS,
        "budgets": [[b[0], b[1]] for b in BUDGETS],
        "styles": [[s[0], s[1], s[2], s[3]] for s in STYLES],
    }
