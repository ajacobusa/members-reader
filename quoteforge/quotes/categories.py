# Maps every occasion category → subcategories → mood → Unsplash search keyword

CATEGORIES: dict[str, dict] = {
    "Faith & Spiritual": {
        "subcategories": [
            "Christian encouragement",
            "Prayer & hope",
            "General spiritual",
            "Gratitude & blessings",
            "Islamic peace",
            "Jewish wisdom",
        ],
        "mood": "uplifting",
        "unsplash_keyword": "golden light sunrise cross",
    },
    "Healing & Wellness": {
        "subcategories": [
            "Mental health & anxiety",
            "Grief & loss",
            "Self-love",
            "Sobriety & recovery",
            "Body positivity",
        ],
        "mood": "calm",
        "unsplash_keyword": "soft nature morning mist",
    },
    "Love & Relationships": {
        "subcategories": [
            "Anniversary",
            "Wedding & newlywed",
            "Friendship",
            "Motherhood",
            "Fatherhood",
            "Family bonds",
        ],
        "mood": "warm",
        "unsplash_keyword": "soft bokeh flowers sunset",
    },
    "Milestone Celebrations": {
        "subcategories": [
            "Birthday",
            "Graduation",
            "Retirement",
            "New baby",
            "New home",
            "Promotion",
        ],
        "mood": "joyful",
        "unsplash_keyword": "confetti celebration light",
    },
    "Motivation & Mindset": {
        "subcategories": [
            "Entrepreneur & hustle",
            "Growth mindset",
            "Morning routine",
            "Resilience",
            "Office & workspace",
            "Leadership",
        ],
        "mood": "powerful",
        "unsplash_keyword": "mountain peak sunrise dramatic",
    },
    "Holidays & Seasonal": {
        "subcategories": [
            "Christmas",
            "Easter",
            "Thanksgiving",
            "Valentine's Day",
            "Mother's Day",
            "Father's Day",
            "4th of July",
            "Halloween",
            "New Year",
        ],
        "mood": "festive",
        "unsplash_keyword": "holiday seasonal nature",
    },
    "Civic & Political": {
        "subcategories": [
            "Patriotism & freedom",
            "Voting & democracy",
            "Military & veteran honor",
            "First responders",
            "Community & unity",
        ],
        "mood": "bold",
        "unsplash_keyword": "american flag landscape blue sky",
    },
    "Nature & Peace": {
        "subcategories": [
            "Mountain serenity",
            "Beach & ocean",
            "Forest stillness",
            "Sunrise hope",
            "Starry night",
        ],
        "mood": "serene",
        "unsplash_keyword": "scenic nature landscape peaceful",
    },
    "Office & Business": {
        "subcategories": [
            "Teamwork",
            "Innovation",
            "Success mindset",
            "Work-life balance",
        ],
        "mood": "professional",
        "unsplash_keyword": "clean minimal desk light",
    },
}

MOOD_TO_UNSPLASH: dict[str, str] = {
    "uplifting": "golden light sunrise hope sky",
    "calm": "soft morning mist nature gentle",
    "warm": "soft bokeh flowers warm light",
    "joyful": "bright colorful celebration joy",
    "powerful": "dramatic mountain peak storm epic",
    "festive": "holiday seasonal cozy warm light",
    "bold": "strong landscape flag sky dramatic",
    "serene": "peaceful lake forest misty calm",
    "professional": "clean minimal modern light",
}


def get_mood(category: str, subcategory: str) -> str:
    """Return the mood string for a given category."""
    return CATEGORIES.get(category, {}).get("mood", "serene")


def get_unsplash_keyword(mood: str) -> str:
    """Return Unsplash search keyword for a given mood."""
    return MOOD_TO_UNSPLASH.get(mood, "scenic nature landscape")
