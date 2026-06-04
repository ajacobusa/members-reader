"""Complete occasion taxonomy for a year-round personalized poster business.

The strategy: have a product for almost every reason someone buys a meaningful
gift during the calendar year. This module is the single source of truth for
those occasions, organized by calendar month, religion, relationship,
profession, milestone, and emotional life event — and a monthly planner that
tells you which occasions to create listings for right now.
"""
from datetime import datetime

# ── Calendar: occasions that spike each month ────────────────────
MONTHLY_OCCASIONS: dict[str, list[str]] = {
    "January": [
        "New Year's Day", "Personalized Goals Poster", "Letter From Future Self",
        "Vision Board Poster", "Family Goals For The Year",
        "New Job", "First Promotion", "New Career Path", "Business Launch",
        "College Semester Start", "Future Dentist", "Future Nurse",
        "Future Physician", "Future Teacher",
    ],
    "February": [
        "Valentine's Day", "For My Husband", "For My Wife", "For My Boyfriend",
        "For My Girlfriend", "For My Fiancé", "For My Fiancée",
        "Engagement", "Proposal Story", "The Day I Knew",
        "Galentine's Day", "Best Friend Appreciation",
    ],
    "March": [
        "Spring Encouragement", "Growth", "Renewal", "Fresh Start",
        "Women's History Month", "For My Mother", "For My Daughter", "For My Mentor",
    ],
    "April": [
        "Easter", "Resurrection Art", "Christian Blessings", "Family Faith Poster",
        "First Communion", "Personalized Prayer", "Confirmation",
        "Faith Journey", "Child Baptism", "Adult Baptism",
    ],
    "May": [
        "Mother's Day", "For Mom", "For Grandma", "For Stepmom", "For Mother-in-Law",
        "Graduation — High School", "Graduation — College", "Graduation — Graduate School",
        "Graduation — Medical School", "Graduation — Dental School",
        "Graduation — Nursing School", "Graduation — Law School",
    ],
    "June": [
        "Father's Day", "For Dad", "For Grandpa", "For Stepdad",
        "Wedding — Bride", "Wedding — Groom", "Parents Of The Bride",
        "Parents Of The Groom",
        "Anniversary — 1 Year", "Anniversary — 5 Years", "Anniversary — 10 Years",
        "Anniversary — 25 Years", "Anniversary — 50 Years",
    ],
    "July": [
        "Independence Day", "Military Appreciation", "Deployment", "Homecoming",
        "Retirement",
    ],
    "August": [
        "Back To School", "Teacher Gift", "College Student Gift",
        "Moving To College", "Dorm Inspiration", "Future Professional Poster",
    ],
    "September": [
        "Grandparents Day", "Labor Day", "Teacher Appreciation", "Fall Collection",
    ],
    "October": [
        "Pregnancy Announcement", "New Baby", "Adoption", "Halloween",
        "Pastor Appreciation",
    ],
    "November": [
        "Thanksgiving", "Family Gratitude Poster", "Family Legacy Poster",
        "Veterans Day", "Veteran Recognition", "Military Service Gift",
    ],
    "December": [
        "Christmas", "Christian Gift", "Family Gift", "Personalized Blessing",
        "Hanukkah", "End Of Year Reflection", "Family Memory Poster",
        "Year-In-Review Keepsake",
    ],
}

# ── Religious occasions ──────────────────────────────────────────
RELIGIOUS_OCCASIONS: dict[str, list[str]] = {
    "Christian": [
        "Baptism", "Confirmation", "First Communion", "Easter", "Christmas",
        "Church Anniversary", "Pastor Appreciation", "Mission Trip",
        "Prayer Poster", "Personalized Bible Verse", "Faith During Difficult Times",
        "Christian Graduation", "Christian Wedding",
    ],
    "Jewish": [
        "Bar Mitzvah", "Bat Mitzvah", "Hanukkah", "Passover",
    ],
    "Hindu": [
        "Diwali", "Navratri", "House Blessing", "Hindu Wedding Gift",
    ],
    "Muslim": [
        "Ramadan", "Eid al-Fitr", "Eid al-Adha", "Hajj Celebration",
    ],
}

# ── Wedding industry ─────────────────────────────────────────────
WEDDING_OCCASIONS: list[str] = [
    "Proposal", "Engagement", "Bridal Shower", "Wedding Day", "Honeymoon",
    "Anniversary", "Vow Renewal", "New Home After Marriage",
]

# ── Family & birthday milestones ─────────────────────────────────
FAMILY_MILESTONES: list[str] = [
    "New Baby", "Gender Reveal", "Adoption", "First Birthday", "Sweet 16",
    "Quinceañera", "18th Birthday", "21st Birthday", "30th Birthday",
    "40th Birthday", "50th Birthday", "60th Birthday", "70th Birthday",
    "80th Birthday", "90th Birthday", "100th Birthday",
]

# ── Career & education milestones ────────────────────────────────
CAREER_MILESTONES: list[str] = [
    "First Job", "Promotion", "Career Change", "Retirement", "New Business",
    "Entrepreneur Launch", "Professional Licensure",
]
EDUCATION_MILESTONES: list[str] = [
    "Kindergarten Graduation", "Elementary Graduation", "Middle School Graduation",
    "High School Graduation", "College Graduation", "Master's Degree", "PhD",
    "Dental School", "Medical School", "Nursing School",
]

# ── Emotional / life events (highest margin) ─────────────────────
EMOTIONAL_EVENTS: list[str] = [
    "Loss Of Parent", "Loss Of Child", "Loss Of Spouse", "Pet Memorial",
    "Divorce Recovery", "Cancer Survivor", "Sobriety Milestone",
    "Mental Health Recovery", "Grief Support", "Long Distance Relationship",
    "Infertility Journey", "Foster Care Adoption",
]

# ── Relationships ────────────────────────────────────────────────
RELATIONSHIPS: list[str] = [
    "Daughter", "Son", "Mother", "Father", "Sister", "Brother",
    "Grandmother", "Grandfather", "Aunt", "Uncle", "Cousin",
    "Godmother", "Godfather", "Best Friend", "Mentor", "Teacher", "Coach",
]

# ── Civic / political (recurring federal elections) ──────────────
CIVIC_OCCASIONS: list[str] = [
    "Election Day", "Vote", "Your Voice Matters", "First-Time Voter",
    "Civic Pride", "Midterm Election", "Presidential Election",
    "Inauguration Day", "Patriotic / Freedom", "Get Out The Vote",
    "New Citizen / Naturalization",
]

# ── Profession-specific ──────────────────────────────────────────
PROFESSIONS: list[str] = [
    "Dentist", "Dental Hygienist", "Orthodontist", "Nurse", "Physician",
    "Pharmacist", "Teacher", "Engineer", "Lawyer", "Veterinarian",
    "First Responder", "Police Officer", "Firefighter", "Military",
]

# ── High-profit evergreen categories (sell year after year) ──────
EVERGREEN_CATEGORIES: list[str] = [
    "Christian Personalized Gifts", "Graduation Gifts", "Daughter/Son Gifts",
    "Wedding & Anniversary Gifts", "Memorial Gifts", "New Baby Gifts",
    "Retirement Gifts", "Healthcare Profession Gifts", "Teacher Gifts",
    "Future Career Vision Posters",
]


# ── Helpers ──────────────────────────────────────────────────────

def get_month_occasions(month: int | str, now: datetime | None = None) -> list[str]:
    """Occasions that spike in a given month (1-12 or month name)."""
    if isinstance(month, int):
        name = datetime(2000, month, 1).strftime("%B")
    else:
        name = month
    return MONTHLY_OCCASIONS.get(name, [])


def get_current_month_plan(now: datetime | None = None) -> dict:
    """What to focus listings on right now, plus next month to prep ahead."""
    now = now or datetime.now()
    this_name = now.strftime("%B")
    next_month = (now.month % 12) + 1
    next_name = datetime(2000, next_month, 1).strftime("%B")
    return {
        "month": this_name,
        "this_month": get_month_occasions(now.month),
        "prep_next_month": next_name,
        "next_month": get_month_occasions(next_month),
        "evergreen_always_list": EVERGREEN_CATEGORIES,
    }


def all_occasions() -> list[str]:
    """Every distinct occasion across all groups (de-duplicated, sorted)."""
    seen: set[str] = set()
    for group in MONTHLY_OCCASIONS.values():
        seen.update(group)
    for group in RELIGIOUS_OCCASIONS.values():
        seen.update(group)
    for group in (WEDDING_OCCASIONS, FAMILY_MILESTONES, CAREER_MILESTONES,
                  EDUCATION_MILESTONES, EMOTIONAL_EVENTS, RELATIONSHIPS,
                  PROFESSIONS, CIVIC_OCCASIONS):
        seen.update(group)
    return sorted(seen)


def occasion_count() -> int:
    return len(all_occasions())


def coverage_summary() -> dict:
    """How many occasions per group — your year-round coverage at a glance."""
    return {
        "calendar_months": sum(len(v) for v in MONTHLY_OCCASIONS.values()),
        "religious": sum(len(v) for v in RELIGIOUS_OCCASIONS.values()),
        "wedding": len(WEDDING_OCCASIONS),
        "family_milestones": len(FAMILY_MILESTONES),
        "career_milestones": len(CAREER_MILESTONES),
        "education_milestones": len(EDUCATION_MILESTONES),
        "emotional_events": len(EMOTIONAL_EVENTS),
        "relationships": len(RELATIONSHIPS),
        "professions": len(PROFESSIONS),
        "civic": len(CIVIC_OCCASIONS),
        "evergreen": len(EVERGREEN_CATEGORIES),
        "total_distinct_occasions": occasion_count(),
    }
