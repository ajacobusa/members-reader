from pathlib import Path
import re

from quoteforge.quotes.generator import generate_quotes
from quoteforge.quotes.categories import get_mood, get_unsplash_keyword
from quoteforge.images.backgrounds import fetch_background_url
from quoteforge.images.renderer import render_poster
from quoteforge.images.downloader import download_png
from quoteforge.etsy.listings import generate_listing


def _safe_filename(text: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())[:40]
    return f"{index:03d}_{slug}"


def run_pipeline(
    category: str,
    subcategory: str,
    count: int,
    template_uid: str,
    output_dir: Path,
    on_progress: callable = None,
) -> list[dict]:
    """Run full quote→image→listing pipeline. Returns list of result dicts."""
    results = []
    quotes = generate_quotes(category, subcategory, count)
    mood = get_mood(category, subcategory)
    keyword = get_unsplash_keyword(mood)

    for i, quote in enumerate(quotes):
        if on_progress:
            on_progress(i, len(quotes), quote)

        bg_url = fetch_background_url(keyword)
        if not bg_url:
            continue

        image_url = render_poster(template_uid, quote, bg_url)
        if not image_url:
            continue

        filename = _safe_filename(quote, i + 1)
        png_path = download_png(image_url, output_dir / category, filename)
        listing = generate_listing(quote, category, subcategory)

        results.append({"quote": quote, "png_path": png_path, "listing": listing})

    return results
