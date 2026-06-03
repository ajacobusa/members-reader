import os
from pathlib import Path

# API Keys — set these as environment variables or paste directly
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
UNSPLASH_ACCESS_KEY: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
BANNERBEAR_API_KEY: str = os.getenv("BANNERBEAR_API_KEY", "")

# Output
OUTPUT_DIR: Path = Path.home() / "Desktop" / "QuoteForge-Output"

# Poster sizes: (width_px, height_px) at 300 DPI
SIZES: dict[str, tuple[int, int]] = {
    "Poster 18x24": (5400, 7200),
    "Poster 24x36": (7200, 10800),
    "Canvas 16x20": (4800, 6000),
    "Square 12x12": (3600, 3600),
}

# Claude model
CLAUDE_MODEL: str = "claude-sonnet-4-6"
