import os
from pathlib import Path

# API Keys — set these as environment variables or paste directly
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
UNSPLASH_ACCESS_KEY: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
BANNERBEAR_API_KEY: str = os.getenv("BANNERBEAR_API_KEY", "")

# Output
OUTPUT_DIR: Path = Path.home() / "Desktop" / "QuoteForge-Output"

# Claude model
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Bannerbear template UID — set this after creating your template
BANNERBEAR_TEMPLATE_UID: str = os.getenv("BANNERBEAR_TEMPLATE_UID", "YOUR_BANNERBEAR_TEMPLATE_UID")

# Phase 12: All Gelato product sizes at 300 DPI (width_px, height_px)
PRODUCTS: dict[str, dict] = {
    # Posters
    "Poster 18x24 in": {"size": (5400, 7200), "gelato_sku": "poster_18x24", "profit": "medium"},
    "Poster 24x36 in": {"size": (7200, 10800), "gelato_sku": "poster_24x36", "profit": "medium"},
    # Canvas — higher profit
    "Canvas 16x20 in": {"size": (4800, 6000), "gelato_sku": "canvas_16x20", "profit": "high"},
    "Canvas 18x24 in": {"size": (5400, 7200), "gelato_sku": "canvas_18x24", "profit": "high"},
    # Framed prints — higher profit
    "Framed 11x14 in": {"size": (3300, 4200), "gelato_sku": "framed_11x14", "profit": "high"},
    "Framed 16x20 in": {"size": (4800, 6000), "gelato_sku": "framed_16x20", "profit": "high"},
    # Acrylic — premium
    "Acrylic 12x16 in": {"size": (3600, 4800), "gelato_sku": "acrylic_12x16", "profit": "premium"},
    "Acrylic 16x20 in": {"size": (4800, 6000), "gelato_sku": "acrylic_16x20", "profit": "premium"},
    # Metal — premium
    "Metal 12x16 in": {"size": (3600, 4800), "gelato_sku": "metal_12x16", "profit": "premium"},
    "Metal 16x20 in": {"size": (4800, 6000), "gelato_sku": "metal_16x20", "profit": "premium"},
    # Square / social
    "Square 12x12 in": {"size": (3600, 3600), "gelato_sku": "poster_12x12", "profit": "medium"},
}

# Airtable
AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")

# Gelato API (for programmatic order creation)
GELATO_API_KEY: str = os.getenv("GELATO_API_KEY", "")

# Google Drive (for artwork storage)
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

# Canva API
CANVA_API_KEY: str = os.getenv("CANVA_API_KEY", "")

# Pipeline settings
PIPELINE_AUTO_APPROVE_PROOF: bool = False  # True = skip proof step, auto-submit to Gelato
PIPELINE_REVIEW_DELAY_DAYS: int = 14       # days after delivery to send review request
PIPELINE_UPSELL_DELAY_HOURS: int = 2       # hours after order to send upsell message

# Phase 1 priority niches to validate first (20-30 manual listings)
PHASE1_NICHES: list[str] = [
    "Personalized Daughter Gifts",
    "Personalized Son Gifts",
    "Christian Encouragement",
    "Graduation Gifts",
    "Memorial Gifts",
    "Future Dentist Gifts",
    "Custom Love Letters",
    "Personalized Mom Gifts",
]

# Phase 14 bulk catalog: 8 core relationships × quote batches = 800+ listings
BULK_CATALOG_RELATIONSHIPS: list[str] = [
    "Daughter", "Son", "Wife", "Husband", "Mom", "Dad", "Friend", "Graduation",
]
