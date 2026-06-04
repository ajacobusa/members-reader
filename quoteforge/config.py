import os
from pathlib import Path

# Load .env file if present (python-dotenv optional — degrade gracefully)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # dotenv not installed — environment variables still work


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("true", "1", "yes", "on")


# TEST_MODE — when true, pipeline generates mock outputs without calling paid APIs.
# Keep this ON until a full real test order has succeeded end-to-end.
TEST_MODE: bool = _env_bool("TEST_MODE", True)

# API Keys — set these as environment variables or paste directly
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
UNSPLASH_ACCESS_KEY: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
BANNERBEAR_API_KEY: str = os.getenv("BANNERBEAR_API_KEY", "")

# Output
OUTPUT_DIR: Path = Path.home() / "Desktop" / "QuoteForge-Output"

# Claude models.
# Quote/message/SEO generation is short and simple — Haiku 4.5 does it well at
# ~1/3 the cost of Sonnet ($1/$5 per 1M vs $3/$15). Override per env if you want
# higher quality (e.g. set CLAUDE_MODEL=claude-sonnet-4-6).
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

# Bannerbear template UID — set this after creating your template
BANNERBEAR_TEMPLATE_UID: str = os.getenv("BANNERBEAR_TEMPLATE_UID", "YOUR_BANNERBEAR_TEMPLATE_UID")

# Renderer selection: "local" (free, Pillow — default) | "bannerbear" | "canva".
# Local rendering composites the quote over an Unsplash background with Pillow,
# eliminating the Bannerbear subscription ($49/mo) for standard quote posters.
RENDERER: str = os.getenv("RENDERER", "local")

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
GELATO_BASE_URL: str = os.getenv("GELATO_BASE_URL", "https://order.gelatoapis.com")

# Google Drive (for artwork storage)
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")

# Canva API
CANVA_API_KEY: str = os.getenv("CANVA_API_KEY", "")
CANVA_BRAND_TEMPLATE_ID: str = os.getenv("CANVA_BRAND_TEMPLATE_ID", "")

# Etsy API (for webhook verification + order pulling)
ETSY_SHOP_ID: str = os.getenv("ETSY_SHOP_ID", "")
ETSY_API_KEY: str = os.getenv("ETSY_API_KEY", "")
ETSY_WEBHOOK_SECRET: str = os.getenv("ETSY_WEBHOOK_SECRET", "")

# Pipeline settings
PIPELINE_AUTO_APPROVE_PROOF: bool = _env_bool("PIPELINE_AUTO_APPROVE_PROOF", False)
PIPELINE_REVIEW_DELAY_DAYS: int = int(os.getenv("PIPELINE_REVIEW_DELAY_DAYS", "14"))
PIPELINE_UPSELL_DELAY_HOURS: int = int(os.getenv("PIPELINE_UPSELL_DELAY_HOURS", "2"))

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
