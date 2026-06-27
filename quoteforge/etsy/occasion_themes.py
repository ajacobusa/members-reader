"""Subtle occasion themes: an occasion key -> a default {bg, text} colour for the
storefront editor, drawn ENTIRELY from the existing palette (BGCOLORS/TXTCOLORS in
listing_preview.py) so a theme can never introduce an off-brand colour. Applied as the
editor's STARTING colours; a saved design or any manual change overrides. Colour only
("Subtle") - the font is unchanged. Keys match listing_preview._listing_occasion_key.
"""
from __future__ import annotations

import json

_DEFAULT = {"bg": "#103d2e", "text": "#f4efe6"}   # today's default (deep green / cream)

OCCASION_TINTS: dict[str, dict] = {
    "memorial":        {"bg": "#f4efe6", "text": "#103d2e"},
    "faith":           {"bg": "#f4efe6", "text": "#103d2e"},
    "new baby":        {"bg": "#dcd6c8", "text": "#103d2e"},
    "housewarming":    {"bg": "#dcd6c8", "text": "#103d2e"},
    "mother's day":    {"bg": "#dcd6c8", "text": "#103d2e"},
    "wedding":         {"bg": "#f4efe6", "text": "#7a2e2e"},
    "anniversary":     {"bg": "#dcd6c8", "text": "#7a2e2e"},
    "valentine's day": {"bg": "#dcd6c8", "text": "#7a2e2e"},
    "birthday":        {"bg": "#f4efe6", "text": "#c9a84c"},
    "graduation":      {"bg": "#2e3a55", "text": "#f4efe6"},
    "father's day":    {"bg": "#3a2e24", "text": "#f4efe6"},
    "christmas":       {"bg": "#103d2e", "text": "#c9a84c"},
}


def theme_for(occ: str) -> dict:
    """The default {bg, text} for an occasion key; today's default for unknown/empty."""
    return OCCASION_TINTS.get((occ or "").strip().lower(), _DEFAULT)


def tints_json() -> str:
    """The occasion->tint map as compact JSON, for embedding in the storefront page."""
    return json.dumps(OCCASION_TINTS, separators=(",", ":"))
