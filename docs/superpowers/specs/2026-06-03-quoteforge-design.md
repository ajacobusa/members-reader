# QuoteForge — Design Spec
**Date:** 2026-06-03
**Goal:** Automated, professional-grade wall art generator that produces print-ready 300 DPI PNG posters for every occasion, sold via Gelato + Etsy.

---

## What Makes QuoteForge Unique

Most Etsy sellers use Canva manually — one design at a time, copy-paste quotes, same generic templates. QuoteForge beats them on every dimension:

| Competitor | QuoteForge |
|---|---|
| Manual Canva one-at-a-time | Generates 50+ designs per hour |
| Generic stock quotes | AI-written originals — never seen before |
| Random background + quote | Emotion-matched: sad quote → muted tones, power quote → bold sunrise |
| No SEO strategy | Auto-generates Etsy-optimized titles, tags, descriptions |
| One size | Multi-size per design (poster 18×24, canvas 16×20, square) |

---

## Occasion Categories (Full Coverage)

### Faith & Spiritual
- Christian encouragement, prayer, Bible-inspired (original paraphrases)
- General spiritual, gratitude, blessings
- Islamic peace phrases, Jewish wisdom

### Healing & Wellness
- Mental health, anxiety relief, grief support
- Self-love, body positivity, sobriety milestones

### Love & Relationships
- Anniversary, wedding, marriage, newlywed
- Friendship, family bonds, motherhood, fatherhood

### Milestone Celebrations
- Birthday (all ages), graduation, retirement
- New baby, new home, new job, promotion

### Motivation & Mindset
- Entrepreneur, hustle, business leadership
- Morning routine, growth mindset, resilience
- Office and workspace decor

### Holidays & Seasonal
- Christmas, Easter, Thanksgiving, Halloween
- Valentine's Day, Mother's Day, Father's Day
- 4th of July, Memorial Day, Labor Day
- New Year, Spring/Summer/Fall/Winter collections

### Civic & Political
- Patriotism, freedom, democracy, voting
- Military/veteran honor, first responders
- Community, unity, civic pride

### Nature & Peace
- Mountain serenity, beach calm, forest stillness
- Sunrise hope, starry night wonder, rain renewal

---

## Design Intelligence (What Makes It Unique)

### 1. Emotion-Matched Backgrounds
Quote mood is analyzed and matched to background:
- Power/strength → bold sunrise, mountain peak, stormy sea
- Peace/calm → soft beach, misty lake, forest morning
- Faith/hope → golden light, cross silhouettes, sunrise over water
- Love → soft florals, warm sunset, bokeh lights
- Patriotic → American landscape, flag, eagles, blue sky

### 2. Typography Intelligence
- Font auto-selected per mood: bold sans-serif for motivation, elegant serif for faith, script for love
- Font size auto-scales to quote length so it always fits perfectly
- Text shadow and color auto-adjusted for background contrast (always readable)
- Quote + attribution on separate lines with proper hierarchy

### 3. Collection Coherence
Designs in the same collection share:
- Consistent color palette
- Same font family
- Matching layout grid
- Cohesive visual identity buyers recognize

### 4. SEO-Optimized Listing Engine
For every design, auto-generates:
- Etsy title (max 140 chars, keyword-rich)
- 13 Etsy tags (max 20 chars each)
- Full listing description (300+ words)
- Suggested price range based on size/category

---

## Output Formats

| Product | Size | DPI | Format |
|---|---|---|---|
| Poster | 18×24 in | 300 | PNG |
| Poster Large | 24×36 in | 300 | PNG |
| Canvas | 16×20 in | 300 | PNG |
| Square | 12×12 in | 300 | PNG |
| Mug wrap | 11oz template | 300 | PNG |

---

## Tech Stack

| Role | Tool | Cost |
|---|---|---|
| GUI (desktop app) | Python + Tkinter | Free |
| Quote generation | Claude API (claude-sonnet-4-6) | ~$5/mo |
| Image rendering | Bannerbear API | $49/mo |
| Background photos | Unsplash API | Free |
| Fonts | Google Fonts (bundled) | Free |
| SEO copy | Claude API | Included above |
| Listing export | CSV export | Free |
| One-click installer | Python + batch script | Free |

---

## User Flow (Double-Click App)

```
1. Double-click QuoteForge.bat
2. App window opens
3. Select category (dropdown)
4. Select sub-category
5. Enter number of designs (e.g., 10)
6. Select output sizes (checkboxes)
7. Click "Generate"
8. Progress bar shows real-time status
9. "Done! 10 designs saved to Desktop/QuoteForge-Output/"
10. Open folder → drag PNGs into Gelato
```

---

## File Structure

```
quoteforge/
  QuoteForge.bat          # Double-click launcher (Windows)
  main.py                 # App entry point
  config.py               # API keys, sizes, settings
  install.bat             # One-time setup installer
  requirements.txt
  quotes/
    generator.py          # Claude API quote generation
    library.py            # 500+ built-in public domain quotes
    categories.py         # All occasion categories + moods
  images/
    backgrounds.py        # Unsplash API fetch by mood
    renderer.py           # Bannerbear API render
    downloader.py         # Save PNGs to output folder
  etsy/
    listings.py           # Claude API SEO titles/tags/descriptions
    exporter.py           # Export listing CSV for Etsy bulk upload
  gui/
    app.py                # Tkinter main window
    progress.py           # Progress bar + status label
  assets/
    fonts/                # Bundled Google Fonts (offline fallback)
    backgrounds/          # 50 bundled fallback backgrounds
  output/                 # Generated designs land here
  docs/
    SETUP.md              # Step-by-step setup guide (non-technical)
    GELATO-GUIDE.md       # How to upload to Gelato
    ETSY-GUIDE.md         # How to publish on Etsy
```

---

## Competitive Edge Summary

1. **No one automates all 10 occasion categories** — most shops focus on 1-2 niches
2. **Emotion-matched design** — background + font + color always matches quote mood
3. **Auto-SEO** — Etsy listing written before you even open Etsy
4. **Collection coherence** — buyers see a professional brand, not random designs
5. **Scale** — 100 listings in a day; competitors manually make 5
