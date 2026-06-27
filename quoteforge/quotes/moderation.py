"""Lightweight moderation for AI-generated personalization text.

A safety net ON TOP of the prompt-level instructions: drops empty / too-short
variations and any output containing profanity, so a bad generation never reaches
a customer-facing poster. Word-boundary matched to avoid false positives
(e.g. 'class', 'assess', 'Scunthorpe').
"""
import re

# Conservative blocklist of clearly-offensive terms (word-boundary matched). Mild
# words with many legitimate sentimental/religious uses (damn, hell, piss) are
# intentionally excluded to avoid filtering genuine heartfelt text.
_PROFANITY = {
    "fuck", "shit", "bitch", "bastard", "asshole", "dick", "cunt", "slut",
    "whore", "nigger", "faggot", "retard", "cock", "pussy",
}
_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _PROFANITY) + r")\b",
                 re.IGNORECASE)

MIN_LENGTH = 15  # chars after strip; shorter = a truncated/near-empty generation


def is_clean(text: str) -> bool:
    """True when the text contains no blocklisted profanity."""
    return not _RE.search(text or "")


def acceptable(text: str, min_length: int = MIN_LENGTH) -> bool:
    """True when text is non-empty, long enough, and profanity-free."""
    t = (text or "").strip()
    return len(t) >= min_length and is_clean(t)


def filter_variations(variations, min_length: int = MIN_LENGTH) -> list:
    """Keep only acceptable variations (non-empty, long enough, clean)."""
    return [v for v in (variations or []) if acceptable(v, min_length)]
