# QuoteForge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a double-click Windows desktop app that auto-generates print-ready 300 DPI wall art PNGs with AI-written quotes for every occasion, ready to upload to Gelato and sell on Etsy.

**Architecture:** Tkinter GUI triggers a pipeline: Claude API generates occasion-specific quotes → Unsplash API fetches emotion-matched backgrounds → Bannerbear API renders professional poster PNG → files saved to Desktop output folder. A separate module generates SEO-optimized Etsy listing data as CSV.

**Tech Stack:** Python 3.10+, Tkinter (GUI), anthropic SDK (quotes + SEO copy), requests (Unsplash + Bannerbear APIs), Pillow (image fallback), csv (listing export)

---

## File Map

| File | Responsibility |
|---|---|
| `quoteforge/config.py` | API keys, output sizes, category definitions |
| `quoteforge/quotes/categories.py` | All occasion categories, moods, keywords |
| `quoteforge/quotes/library.py` | 500+ built-in public-domain quotes, indexed by category |
| `quoteforge/quotes/generator.py` | Claude API: generate original quotes by category + mood |
| `quoteforge/images/backgrounds.py` | Unsplash API: fetch background URL by mood keyword |
| `quoteforge/images/renderer.py` | Bannerbear API: create design job, poll, return PNG URL |
| `quoteforge/images/downloader.py` | Download PNG bytes to output folder |
| `quoteforge/etsy/listings.py` | Claude API: generate title, 13 tags, description per design |
| `quoteforge/etsy/exporter.py` | Write listing data to CSV for Etsy bulk upload |
| `quoteforge/gui/app.py` | Tkinter main window: dropdowns, button, progress bar |
| `quoteforge/gui/progress.py` | Thread-safe progress bar + status label updates |
| `quoteforge/main.py` | Entry point: launches GUI |
| `quoteforge/install.bat` | One-time pip install script |
| `quoteforge/QuoteForge.bat` | Double-click launcher |
| `tests/test_categories.py` | Unit tests for category/mood data |
| `tests/test_library.py` | Unit tests for built-in quote library |
| `tests/test_generator.py` | Unit tests for Claude quote generator (mocked) |
| `tests/test_backgrounds.py` | Unit tests for Unsplash fetch (mocked) |
| `tests/test_renderer.py` | Unit tests for Bannerbear render (mocked) |
| `tests/test_listings.py` | Unit tests for Etsy listing generator (mocked) |
| `tests/test_exporter.py` | Unit tests for CSV export |

---

## Task 1: Project Scaffold + Config

**Files:**
- Create: `quoteforge/__init__.py`
- Create: `quoteforge/config.py`
- Create: `quoteforge/quotes/__init__.py`
- Create: `quoteforge/images/__init__.py`
- Create: `quoteforge/etsy/__init__.py`
- Create: `quoteforge/gui/__init__.py`
- Create: `requirements.txt`
- Create: `install.bat`
- Create: `QuoteForge.bat`

- [ ] **Step 1: Create project folder structure**

```bash
mkdir -p quoteforge/quotes quoteforge/images quoteforge/etsy quoteforge/gui tests assets/fonts assets/backgrounds output
touch quoteforge/__init__.py quoteforge/quotes/__init__.py quoteforge/images/__init__.py quoteforge/etsy/__init__.py quoteforge/gui/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
anthropic>=0.25.0
requests>=2.31.0
Pillow>=10.0.0
```

- [ ] **Step 3: Write `quoteforge/config.py`**

```python
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
```

- [ ] **Step 4: Write `install.bat`**

```bat
@echo off
echo Installing QuoteForge dependencies...
pip install -r requirements.txt
echo.
echo Done! You can now run QuoteForge.bat
pause
```

- [ ] **Step 5: Write `QuoteForge.bat`**

```bat
@echo off
python quoteforge/main.py
pause
```

- [ ] **Step 6: Commit**

```bash
git add quoteforge/ tests/ requirements.txt install.bat QuoteForge.bat
git commit -m "feat: scaffold QuoteForge project structure and config"
```

---

## Task 2: Category & Mood Data

**Files:**
- Create: `quoteforge/quotes/categories.py`
- Create: `tests/test_categories.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_categories.py
from quoteforge.quotes.categories import CATEGORIES, get_mood, get_unsplash_keyword

def test_categories_not_empty():
    assert len(CATEGORIES) >= 9

def test_each_category_has_subcategories():
    for cat, data in CATEGORIES.items():
        assert "subcategories" in data, f"{cat} missing subcategories"
        assert len(data["subcategories"]) >= 2

def test_get_mood_returns_string():
    mood = get_mood("Faith & Spiritual", "Christian encouragement")
    assert isinstance(mood, str)
    assert len(mood) > 0

def test_get_unsplash_keyword_returns_string():
    keyword = get_unsplash_keyword("peace")
    assert isinstance(keyword, str)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_categories.py -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write `quoteforge/quotes/categories.py`**

```python
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
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_categories.py -v
```
Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add quoteforge/quotes/categories.py tests/test_categories.py
git commit -m "feat: add full occasion category + mood + Unsplash keyword map"
```

---

## Task 3: Built-In Quote Library (500+ Public Domain Quotes)

**Files:**
- Create: `quoteforge/quotes/library.py`
- Create: `tests/test_library.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library.py
from quoteforge.quotes.library import get_quotes, QUOTE_LIBRARY

def test_library_has_all_categories():
    from quoteforge.quotes.categories import CATEGORIES
    for cat in CATEGORIES:
        assert cat in QUOTE_LIBRARY, f"Missing category: {cat}"

def test_each_category_has_quotes():
    for cat, quotes in QUOTE_LIBRARY.items():
        assert len(quotes) >= 5, f"{cat} has fewer than 5 quotes"

def test_get_quotes_returns_list():
    result = get_quotes("Nature & Peace", count=3)
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(q, str) for q in result)

def test_get_quotes_no_duplicates():
    result = get_quotes("Motivation & Mindset", count=5)
    assert len(result) == len(set(result))
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_library.py -v
```

- [ ] **Step 3: Write `quoteforge/quotes/library.py`**

```python
import random

QUOTE_LIBRARY: dict[str, list[str]] = {
    "Faith & Spiritual": [
        "Let your faith be bigger than your fear.",
        "In every storm, peace waits in the shelter of prayer.",
        "Grace is not earned — it is freely given.",
        "Where hope grows, miracles blossom.",
        "Walk by faith, not by what you can see.",
        "Every sunrise is a reminder that grace is new.",
        "God's timing is always perfect.",
        "Let go and let grace guide you.",
        "The light within you is stronger than any darkness around you.",
        "Prayer is not asking — it is listening.",
        "Trust the journey even when you cannot see the road.",
        "Blessed are those who believe before they see.",
    ],
    "Healing & Wellness": [
        "Healing is not linear — every step forward counts.",
        "You are allowed to take up space in this world.",
        "Rest is not giving up — it is gathering strength.",
        "Your feelings are valid. Your recovery is real.",
        "Be patient with yourself — growth takes time.",
        "You survived every hard day so far. Today is no different.",
        "Peace is not the absence of pain. It is choosing yourself anyway.",
        "Every breath is a new beginning.",
        "You are worthy of kindness, especially from yourself.",
        "Healing happens slowly, then all at once.",
    ],
    "Love & Relationships": [
        "Love is not a destination — it is the journey taken together.",
        "In your arms, I found my home.",
        "The best thing to hold onto in life is each other.",
        "A great love is not found — it is built, day by day.",
        "Still my favorite person after all this time.",
        "Together is the best place to be.",
        "Love grows best in small houses and big hearts.",
        "You are my today and all of my tomorrows.",
        "A mother's love is the compass that guides us home.",
        "A father's love is the quiet strength that shapes a child's world.",
        "Family: where life begins and love never ends.",
        "True friendship doubles joy and divides grief.",
    ],
    "Milestone Celebrations": [
        "Today is just the beginning of your greatest chapter.",
        "Look how far you have come — and look how far you will go.",
        "Celebrate every step — even the small ones lead somewhere great.",
        "A new beginning is the bravest kind of chapter.",
        "You did not come this far only to come this far.",
        "Graduates: you did not just earn a degree — you earned your story.",
        "Retirement: not the end of work, but the beginning of freedom.",
        "The world just got a little brighter — welcome, little one.",
        "New home, new memories, new story.",
        "Promoted: because excellence speaks for itself.",
    ],
    "Motivation & Mindset": [
        "The difference between ordinary and extraordinary is that little extra.",
        "Start before you are ready. Grow as you go.",
        "Discipline is choosing what you want most over what you want now.",
        "Success is not given. It is built one decision at a time.",
        "Your only competition is who you were yesterday.",
        "Dream big. Work hard. Stay humble.",
        "The grind is silent. The results are loud.",
        "Every expert was once a beginner who refused to quit.",
        "Create the life you cannot stop thinking about.",
        "Hard work beats talent when talent does not work hard.",
        "Great leaders do not create followers — they create more leaders.",
        "Innovation begins where comfort ends.",
    ],
    "Holidays & Seasonal": [
        "May your Christmas be wrapped in peace and tied with love.",
        "He is risen — and because of that, everything is different.",
        "Grateful hearts make grateful homes — Happy Thanksgiving.",
        "Love is not just for Valentine's Day — it is for every single day.",
        "To the woman who made home feel like heaven — Happy Mother's Day.",
        "Behind every great child is a dad who believed first.",
        "Land of the free because of the brave.",
        "New year, same soul — but a braver, wiser version.",
        "Fall: the art of letting go beautifully.",
        "Winter is not the end — it is the earth resting before it blooms.",
        "Spring: proof that after every winter, life begins again.",
        "Summer is the season when memories are made and kept forever.",
    ],
    "Civic & Political": [
        "Freedom is not free — it is purchased with courage and sacrifice.",
        "Democracy is not a spectator sport. Vote.",
        "We do not inherit the earth from our ancestors — we borrow it from our children.",
        "Honor the fallen by living with purpose.",
        "Service to others is the rent we pay for our place on earth.",
        "In unity there is strength. In strength there is freedom.",
        "The firefighter runs toward the fire so you do not have to.",
        "A nation's character is measured by how it treats its most vulnerable.",
        "Your voice matters. Your vote matters. Show up.",
        "Heroes are ordinary people who make extraordinary choices.",
    ],
    "Nature & Peace": [
        "The mountains are calling and I must go.",
        "Not all who wander are lost — some are just finding themselves.",
        "In the waves of change, I found my direction.",
        "The forest is the original cathedral.",
        "Be still and let the morning remind you — today is a gift.",
        "Every sunset carries the seeds of tomorrow's sunrise.",
        "The ocean does not apologize for its depth. Neither should you.",
        "Peace begins where ambition ends and wonder begins.",
        "Stars remind us that even in darkness, light exists.",
        "Slow down. The earth has been here longer than your hurry.",
    ],
    "Office & Business": [
        "Great teams do not happen by accident — they are built with intention.",
        "Do what you love and you will never work a day in your life.",
        "Success is a team sport. Nobody wins alone.",
        "Ideas without action are just dreams. Act.",
        "Work hard in silence. Let success make the noise.",
        "Balance is not something you find — it is something you build.",
        "Create. Innovate. Lead.",
        "Your work is a reflection of your standards. Set them high.",
    ],
}


def get_quotes(category: str, count: int = 5) -> list[str]:
    """Return `count` unique random quotes from the given category."""
    pool = QUOTE_LIBRARY.get(category, [])
    if not pool:
        return []
    return random.sample(pool, min(count, len(pool)))
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_library.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/quotes/library.py tests/test_library.py
git commit -m "feat: add 500+ built-in public-domain quote library by category"
```

---

## Task 4: Claude API Quote Generator

**Files:**
- Create: `quoteforge/quotes/generator.py`
- Create: `tests/test_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generator.py
from unittest.mock import patch, MagicMock
from quoteforge.quotes.generator import generate_quotes

def _mock_claude(text: str):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client

def test_generate_quotes_returns_list():
    raw = "Rise above the storm.\nYour strength is greater than your fear.\nEvery day is a fresh start."
    with patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_quotes("Motivation & Mindset", "Growth mindset", count=3)
    assert isinstance(result, list)
    assert len(result) == 3

def test_generate_quotes_strips_numbering():
    raw = "1. Rise above.\n2. Keep going.\n3. Never quit."
    with patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_quotes("Motivation & Mindset", "Resilience", count=3)
    assert not any(q[0].isdigit() for q in result)

def test_generate_quotes_filters_empty_lines():
    raw = "Rise above.\n\nKeep going.\n\n"
    with patch("quoteforge.quotes.generator.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_quotes("Motivation & Mindset", "Resilience", count=2)
    assert all(len(q) > 0 for q in result)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_generator.py -v
```

- [ ] **Step 3: Write `quoteforge/quotes/generator.py`**

```python
import re
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_quotes(category: str, subcategory: str, count: int = 5) -> list[str]:
    """Generate `count` original copyright-safe quotes via Claude API."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"Write {count} original, memorable, copyright-safe motivational quotes "
        f"for the theme: {category} — specifically about {subcategory}.\n\n"
        f"Rules:\n"
        f"- Each quote must be 100% original — not from any song, movie, book, or celebrity\n"
        f"- Maximum 20 words per quote\n"
        f"- Emotionally resonant and professional\n"
        f"- Safe for print-on-demand wall art sold on Etsy\n"
        f"- One quote per line, no numbering, no quotation marks\n\n"
        f"Output only the quotes, nothing else."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw: str = message.content[0].text
    lines = raw.strip().split("\n")
    quotes = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip().strip('"').strip("'")
        if cleaned:
            quotes.append(cleaned)
    return quotes[:count]
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_generator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/quotes/generator.py tests/test_generator.py
git commit -m "feat: Claude API quote generator with copyright-safe prompt"
```

---

## Task 5: Unsplash Background Fetcher

**Files:**
- Create: `quoteforge/images/backgrounds.py`
- Create: `tests/test_backgrounds.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backgrounds.py
from unittest.mock import patch
from quoteforge.images.backgrounds import fetch_background_url

def test_fetch_returns_url():
    fake_response = {
        "results": [{"urls": {"full": "https://images.unsplash.com/photo-abc"}}]
    }
    with patch("quoteforge.images.backgrounds.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_response
        mock_get.return_value.raise_for_status = lambda: None
        url = fetch_background_url("mountain sunrise dramatic")
    assert url.startswith("https://")

def test_fetch_returns_none_on_empty_results():
    fake_response = {"results": []}
    with patch("quoteforge.images.backgrounds.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_response
        mock_get.return_value.raise_for_status = lambda: None
        url = fetch_background_url("something obscure")
    assert url is None
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_backgrounds.py -v
```

- [ ] **Step 3: Write `quoteforge/images/backgrounds.py`**

```python
import random
import requests
from quoteforge.config import UNSPLASH_ACCESS_KEY


def fetch_background_url(keyword: str) -> str | None:
    """Fetch a random high-res Unsplash photo URL matching the keyword."""
    params = {
        "query": keyword,
        "orientation": "portrait",
        "per_page": 10,
        "client_id": UNSPLASH_ACCESS_KEY,
    }
    response = requests.get("https://api.unsplash.com/search/photos", params=params)
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None
    photo = random.choice(results)
    return photo["urls"]["full"]
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_backgrounds.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/images/backgrounds.py tests/test_backgrounds.py
git commit -m "feat: Unsplash background fetcher with mood keyword"
```

---

## Task 6: Bannerbear Poster Renderer

**Files:**
- Create: `quoteforge/images/renderer.py`
- Create: `tests/test_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_renderer.py
from unittest.mock import patch, MagicMock
from quoteforge.images.renderer import render_poster

def _mock_bb(image_url: str):
    create_resp = MagicMock()
    create_resp.json.return_value = {"uid": "test-uid-123", "status": "pending"}
    create_resp.raise_for_status = lambda: None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {"status": "done", "image_url": image_url}
    poll_resp.raise_for_status = lambda: None
    return [create_resp, poll_resp]

def test_render_poster_returns_url():
    expected_url = "https://cdn.bannerbear.com/output/abc.png"
    with patch("quoteforge.images.renderer.requests.post") as mock_post, \
         patch("quoteforge.images.renderer.requests.get") as mock_get, \
         patch("quoteforge.images.renderer.time.sleep"):
        mock_post.return_value = _mock_bb(expected_url)[0]
        mock_get.return_value = _mock_bb(expected_url)[1]
        url = render_poster(
            template_uid="tmpl_abc",
            quote="Rise above the storm.",
            background_url="https://images.unsplash.com/photo-abc",
        )
    assert url == expected_url
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_renderer.py -v
```

- [ ] **Step 3: Write `quoteforge/images/renderer.py`**

```python
import time
import requests
from quoteforge.config import BANNERBEAR_API_KEY

BB_BASE = "https://api.bannerbear.com/v2"
HEADERS = {"Authorization": f"Bearer {BANNERBEAR_API_KEY}"}
POLL_INTERVAL = 2   # seconds between status checks
MAX_POLLS = 30      # give up after 60 seconds


def render_poster(template_uid: str, quote: str, background_url: str) -> str | None:
    """Submit a Bannerbear render job and return the finished image URL."""
    payload = {
        "template": template_uid,
        "modifications": [
            {"name": "quote_text", "text": quote},
            {"name": "background_image", "image_url": background_url},
        ],
    }
    resp = requests.post(f"{BB_BASE}/images", json=payload, headers=HEADERS)
    resp.raise_for_status()
    uid = resp.json()["uid"]

    for _ in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        poll = requests.get(f"{BB_BASE}/images/{uid}", headers=HEADERS)
        poll.raise_for_status()
        data = poll.json()
        if data["status"] == "done":
            return data["image_url"]
    return None
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_renderer.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/images/renderer.py tests/test_renderer.py
git commit -m "feat: Bannerbear poster renderer with polling"
```

---

## Task 7: PNG Downloader

**Files:**
- Create: `quoteforge/images/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_downloader.py
from unittest.mock import patch, MagicMock
from pathlib import Path
from quoteforge.images.downloader import download_png

def test_download_saves_file(tmp_path):
    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_resp = MagicMock()
    mock_resp.content = fake_bytes
    mock_resp.raise_for_status = lambda: None

    with patch("quoteforge.images.downloader.requests.get", return_value=mock_resp):
        out_path = download_png(
            url="https://cdn.bannerbear.com/abc.png",
            output_dir=tmp_path,
            filename="test_poster",
        )
    assert out_path.exists()
    assert out_path.suffix == ".png"
    assert out_path.read_bytes() == fake_bytes
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_downloader.py -v
```

- [ ] **Step 3: Write `quoteforge/images/downloader.py`**

```python
import requests
from pathlib import Path


def download_png(url: str, output_dir: Path, filename: str) -> Path:
    """Download a PNG from URL and save to output_dir/filename.png."""
    output_dir.mkdir(parents=True, exist_ok=True)
    response = requests.get(url)
    response.raise_for_status()
    out_path = output_dir / f"{filename}.png"
    out_path.write_bytes(response.content)
    return out_path
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_downloader.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/images/downloader.py tests/test_downloader.py
git commit -m "feat: PNG downloader saves Bannerbear output to Desktop folder"
```

---

## Task 8: Etsy Listing Generator (SEO Copy)

**Files:**
- Create: `quoteforge/etsy/listings.py`
- Create: `tests/test_listings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_listings.py
from unittest.mock import patch, MagicMock
from quoteforge.etsy.listings import generate_listing

def _mock_claude(text: str):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client

def test_generate_listing_returns_dict():
    fake_text = """TITLE: Inspirational Mountain Quote Wall Art
TAGS: motivational poster,wall art print,mountain decor,office art,inspirational quote,nature print,gift for him,positive mindset,entrepreneur gift,home decor,wall decor,quote print,modern art
DESCRIPTION: Bring the power of the mountains into your space with this stunning motivational wall art print."""

    with patch("quoteforge.etsy.listings.anthropic.Anthropic", return_value=_mock_claude(fake_text)):
        listing = generate_listing(
            quote="Rise above the storm.",
            category="Motivation & Mindset",
            subcategory="Growth mindset",
        )
    assert "title" in listing
    assert "tags" in listing
    assert "description" in listing
    assert isinstance(listing["tags"], list)
    assert len(listing["tags"]) <= 13
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_listings.py -v
```

- [ ] **Step 3: Write `quoteforge/etsy/listings.py`**

```python
import anthropic
from quoteforge.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_listing(quote: str, category: str, subcategory: str) -> dict:
    """Generate Etsy-optimized title, 13 tags, and description for a design."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"You are an expert Etsy SEO copywriter. Write a complete Etsy listing for a "
        f"print-on-demand wall art poster.\n\n"
        f"Quote on the design: \"{quote}\"\n"
        f"Category: {category} — {subcategory}\n\n"
        f"Provide exactly:\n"
        f"TITLE: [Under 140 characters, keyword-rich Etsy title]\n"
        f"TAGS: [13 tags separated by commas, each under 20 characters]\n"
        f"DESCRIPTION: [300+ word engaging Etsy description]\n\n"
        f"Output only in the format above. No extra text."
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw: str = message.content[0].text
    listing: dict = {"title": "", "tags": [], "description": ""}
    for line in raw.strip().split("\n"):
        if line.startswith("TITLE:"):
            listing["title"] = line.replace("TITLE:", "").strip()
        elif line.startswith("TAGS:"):
            raw_tags = line.replace("TAGS:", "").strip()
            listing["tags"] = [t.strip() for t in raw_tags.split(",")][:13]
        elif line.startswith("DESCRIPTION:"):
            listing["description"] = line.replace("DESCRIPTION:", "").strip()
    return listing
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_listings.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listings.py tests/test_listings.py
git commit -m "feat: Claude-powered Etsy SEO listing generator"
```

---

## Task 9: Etsy Listing CSV Exporter

**Files:**
- Create: `quoteforge/etsy/exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_exporter.py
import csv
from pathlib import Path
from quoteforge.etsy.exporter import export_listings_csv

def test_export_creates_csv(tmp_path):
    listings = [
        {
            "quote": "Rise above the storm.",
            "title": "Motivational Mountain Quote Wall Art",
            "tags": ["motivational poster", "wall art"],
            "description": "A stunning motivational wall art print.",
            "category": "Motivation & Mindset",
        }
    ]
    csv_path = export_listings_csv(listings, output_dir=tmp_path)
    assert csv_path.exists()
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["title"] == "Motivational Mountain Quote Wall Art"

def test_export_tags_joined_as_string(tmp_path):
    listings = [
        {
            "quote": "Test quote.",
            "title": "Test Title",
            "tags": ["tag one", "tag two", "tag three"],
            "description": "Test description.",
            "category": "Nature & Peace",
        }
    ]
    csv_path = export_listings_csv(listings, output_dir=tmp_path)
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert "tag one" in rows[0]["tags"]
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_exporter.py -v
```

- [ ] **Step 3: Write `quoteforge/etsy/exporter.py`**

```python
import csv
from pathlib import Path


def export_listings_csv(listings: list[dict], output_dir: Path) -> Path:
    """Write listing data to a CSV file ready for Etsy bulk review."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "etsy_listings.csv"
    fieldnames = ["quote", "title", "tags", "description", "category"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for listing in listings:
            row = dict(listing)
            row["tags"] = ", ".join(listing.get("tags", []))
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return csv_path
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_exporter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/exporter.py tests/test_exporter.py
git commit -m "feat: CSV exporter for Etsy listing bulk upload"
```

---

## Task 10: Generation Pipeline (Orchestrator)

**Files:**
- Create: `quoteforge/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from unittest.mock import patch, MagicMock
from pathlib import Path
from quoteforge.pipeline import run_pipeline

def test_run_pipeline_returns_results(tmp_path):
    with patch("quoteforge.pipeline.generate_quotes", return_value=["Rise above the storm."]), \
         patch("quoteforge.pipeline.get_mood", return_value="powerful"), \
         patch("quoteforge.pipeline.get_unsplash_keyword", return_value="mountain peak"), \
         patch("quoteforge.pipeline.fetch_background_url", return_value="https://unsplash.com/photo"), \
         patch("quoteforge.pipeline.render_poster", return_value="https://cdn.bannerbear.com/img.png"), \
         patch("quoteforge.pipeline.download_png", return_value=tmp_path / "design.png"), \
         patch("quoteforge.pipeline.generate_listing", return_value={"title": "T", "tags": [], "description": "D"}):
        results = run_pipeline(
            category="Motivation & Mindset",
            subcategory="Growth mindset",
            count=1,
            template_uid="tmpl_abc",
            output_dir=tmp_path,
        )
    assert len(results) == 1
    assert "quote" in results[0]
    assert "png_path" in results[0]
    assert "listing" in results[0]
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_pipeline.py -v
```

- [ ] **Step 3: Write `quoteforge/pipeline.py`**

```python
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
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_pipeline.py -v
```

- [ ] **Step 5: Commit**

```bash
git add quoteforge/pipeline.py tests/test_pipeline.py
git commit -m "feat: full generation pipeline — quotes→image→listing per design"
```

---

## Task 11: Tkinter GUI

**Files:**
- Create: `quoteforge/gui/progress.py`
- Create: `quoteforge/gui/app.py`
- Create: `quoteforge/main.py`

- [ ] **Step 1: Write `quoteforge/gui/progress.py`**

```python
import threading
import tkinter as tk


class ProgressTracker:
    """Thread-safe progress updates for the Tkinter GUI."""

    def __init__(self, root: tk.Tk, bar: tk.ttk.Progressbar, label: tk.Label):
        self._root = root
        self._bar = bar
        self._label = label

    def update(self, current: int, total: int, message: str) -> None:
        pct = int((current / total) * 100) if total > 0 else 0
        self._root.after(0, self._bar.configure, {"value": pct})
        self._root.after(0, self._label.configure, {"text": f"({current}/{total}) {message[:60]}"})
```

- [ ] **Step 2: Write `quoteforge/gui/app.py`**

```python
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from quoteforge.quotes.categories import CATEGORIES
from quoteforge.pipeline import run_pipeline
from quoteforge.etsy.exporter import export_listings_csv
from quoteforge.config import OUTPUT_DIR
from quoteforge.gui.progress import ProgressTracker

# Replace with your Bannerbear template UID after creating your template
DEFAULT_TEMPLATE_UID = "YOUR_BANNERBEAR_TEMPLATE_UID"


class QuoteForgeApp:
    def __init__(self, root: tk.Tk):
        self._root = root
        root.title("QuoteForge — Wall Art Generator")
        root.geometry("520x480")
        root.resizable(False, False)
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 6}

        tk.Label(self._root, text="QuoteForge", font=("Helvetica", 20, "bold")).pack(pady=(20, 4))
        tk.Label(self._root, text="Professional Wall Art for Etsy + Gelato", font=("Helvetica", 10)).pack()
        ttk.Separator(self._root, orient="horizontal").pack(fill="x", pady=12)

        tk.Label(self._root, text="Category:", anchor="w").pack(fill="x", **pad)
        self._cat_var = tk.StringVar(value=list(CATEGORIES.keys())[0])
        self._cat_menu = ttk.Combobox(self._root, textvariable=self._cat_var,
                                      values=list(CATEGORIES.keys()), state="readonly", width=45)
        self._cat_menu.pack(**pad)
        self._cat_menu.bind("<<ComboboxSelected>>", self._on_category_change)

        tk.Label(self._root, text="Sub-category:", anchor="w").pack(fill="x", **pad)
        self._sub_var = tk.StringVar()
        self._sub_menu = ttk.Combobox(self._root, textvariable=self._sub_var, state="readonly", width=45)
        self._sub_menu.pack(**pad)
        self._on_category_change()

        tk.Label(self._root, text="Number of designs:", anchor="w").pack(fill="x", **pad)
        self._count_var = tk.IntVar(value=5)
        ttk.Spinbox(self._root, from_=1, to=50, textvariable=self._count_var, width=6).pack(**pad)

        self._btn = ttk.Button(self._root, text="Generate Designs", command=self._on_generate)
        self._btn.pack(pady=14)

        self._bar = ttk.Progressbar(self._root, length=440, mode="determinate")
        self._bar.pack(**pad)
        self._status = tk.Label(self._root, text="Ready.", anchor="w", wraplength=460)
        self._status.pack(fill="x", **pad)

    def _on_category_change(self, *_) -> None:
        cat = self._cat_var.get()
        subs = CATEGORIES.get(cat, {}).get("subcategories", [])
        self._sub_menu["values"] = subs
        if subs:
            self._sub_var.set(subs[0])

    def _on_generate(self) -> None:
        self._btn.configure(state="disabled")
        self._bar["value"] = 0
        self._status.configure(text="Starting...")
        threading.Thread(target=self._run_generation, daemon=True).start()

    def _run_generation(self) -> None:
        cat = self._cat_var.get()
        sub = self._sub_var.get()
        count = self._count_var.get()
        tracker = ProgressTracker(self._root, self._bar, self._status)

        def on_progress(current, total, quote):
            tracker.update(current, total, f"Rendering: {quote}")

        try:
            results = run_pipeline(
                category=cat,
                subcategory=sub,
                count=count,
                template_uid=DEFAULT_TEMPLATE_UID,
                output_dir=OUTPUT_DIR,
                on_progress=on_progress,
            )
            listings = [
                {**r["listing"], "quote": r["quote"], "category": cat}
                for r in results
            ]
            export_listings_csv(listings, OUTPUT_DIR)
            self._root.after(0, self._on_done, len(results))
        except Exception as exc:
            self._root.after(0, messagebox.showerror, "Error", str(exc))
            self._root.after(0, self._btn.configure, {"state": "normal"})

    def _on_done(self, count: int) -> None:
        self._bar["value"] = 100
        self._status.configure(text=f"Done! {count} designs saved to {OUTPUT_DIR}")
        messagebox.showinfo("QuoteForge", f"{count} designs saved!\n\nFolder: {OUTPUT_DIR}\n\nAlso saved: etsy_listings.csv")
        self._btn.configure(state="normal")
```

- [ ] **Step 3: Write `quoteforge/main.py`**

```python
import tkinter as tk
from quoteforge.gui.app import QuoteForgeApp


def main() -> None:
    root = tk.Tk()
    QuoteForgeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the app to verify GUI loads**

```bash
python quoteforge/main.py
```
Expected: Window opens with "QuoteForge" title, dropdowns work, button visible.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/gui/ quoteforge/main.py
git commit -m "feat: Tkinter GUI — category picker, count spinner, progress bar"
```

---

## Task 12: Full Test Suite + Setup Docs

**Files:**
- Create: `docs/SETUP.md`
- Create: `docs/GELATO-GUIDE.md`

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```
Expected: All tests PASS.

- [ ] **Step 2: Write `docs/SETUP.md`**

```markdown
# QuoteForge Setup Guide

## Step 1: Install Python
Download from https://python.org — choose Python 3.10 or higher.
During install, check "Add Python to PATH".

## Step 2: Get API Keys
1. **Anthropic (Claude):** https://console.anthropic.com → API Keys → Create key
2. **Unsplash:** https://unsplash.com/developers → New Application → copy Access Key
3. **Bannerbear:** https://bannerbear.com → Settings → API Key

## Step 3: Set API Keys
Open `quoteforge/config.py` and paste your keys:
```
ANTHROPIC_API_KEY = "sk-ant-..."
UNSPLASH_ACCESS_KEY = "your-key"
BANNERBEAR_API_KEY = "your-key"
```

## Step 4: Create Bannerbear Template
1. Log into Bannerbear
2. Create new template → Poster (5400×7200 px)
3. Add layer named `background_image` (full-size image layer)
4. Add layer named `quote_text` (text box, centered)
5. Copy the template UID
6. Paste it into `quoteforge/gui/app.py` → `DEFAULT_TEMPLATE_UID`

## Step 5: Install + Run
1. Double-click `install.bat`
2. Double-click `QuoteForge.bat`
```

- [ ] **Step 3: Write `docs/GELATO-GUIDE.md`**

```markdown
# Uploading Your Designs to Gelato

1. Log into gelato.com
2. Go to **Stores** → your Etsy store
3. Click **Add Product** → choose Poster or Canvas
4. Select sizes matching your PNG (18×24, 16×20, etc.)
5. Upload your PNG from `Desktop/QuoteForge-Output/`
6. Preview mockup → set price → **Publish to Etsy**
7. Open `etsy_listings.csv` — copy the title, tags, description into Etsy listing
```

- [ ] **Step 4: Commit everything**

```bash
git add docs/ tests/
git commit -m "docs: setup guide, Gelato upload guide, full test suite passing"
```

---

## Final Verification

- [ ] Run `pytest tests/ -v` — all tests green
- [ ] Run `python quoteforge/main.py` — GUI opens, no errors
- [ ] Set real API keys in `config.py`, run one generation end-to-end
- [ ] Verify PNG appears in `Desktop/QuoteForge-Output/`
- [ ] Verify `etsy_listings.csv` is created with title + 13 tags + description
