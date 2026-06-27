# Subtle occasion themes — design spec

Date: 2026-06-27
Status: approved (pending spec review)
Scope: QuoteForge storefront editor (`quoteforge/`)

## Problem

Every listing's editor opens on the same global default background (deep green
`#103d2e`) regardless of occasion. A Memorial piece and a Birthday piece start
identically, so the customer does more work to reach an occasion-appropriate look
and the first impression is generic.

## Goal

When a customer opens the editor for a listing whose occasion is known, the editor
*starts* on an occasion-appropriate background + text colour drawn from the existing
palette. The customer can still change everything — this only sets the starting
point. "Subtle" level: colour only; the elegant default font is unchanged.

Because the print **is** the canvas (`exportPrint()` renders the customer's canvas to
a high-res PNG, `listing_preview.py:7872/7986`), the tint flows to BOTH the live
preview and the printed piece automatically — no Bannerbear and no server renderer
change required. (Bannerbear is only used for the AI marketing/listing images, not
the customer's order.)

## Non-goals (v1)

- Per-occasion FONTS (Subtle = colour only).
- Apparel (garment colour) and mug (product colour) backgrounds — their background is
  not `SELBG`, so themes do not apply; they keep their own colour.
- The "Balanced" / "Bold" distinctiveness levels (the owner chose Subtle).
- New colours — every tint is an existing palette value.

## Design

### Source of truth: `quoteforge/etsy/occasion_themes.py`

A data table mapping **mood → {bg, text}** (hex, both already in the editor palette),
reusing the existing mood taxonomy in `quoteforge/quotes/categories.py`
(`MOOD_TO_UNSPLASH` keys: uplifting, calm, warm, joyful, powerful, proud, energetic,
festive, bold, serene, professional, adventurous).

Confirmed occasion-family → colour mapping (all from the current palette
`BGCOLORS`/`TXTCOLORS`):

| Occasion family            | bg (hex)   | text (hex) |
|----------------------------|-----------|-----------|
| Memorial / Sympathy        | `#f4efe6` | `#103d2e` |
| Birthday / Celebration     | `#c9a84c` | `#1b1b1f` |
| Wedding / Anniversary      | `#dcd6c8` | `#7a2e2e` |
| Faith / Christian          | `#f4efe6` | `#103d2e` |
| Graduation / Career        | `#2e3a55` | `#f4efe6` |
| New baby / Family          | `#dcd6c8` | `#103d2e` |
| Christmas / Seasonal       | `#103d2e` | `#c9a84c` |
| Default / unknown          | `#103d2e` | `#f4efe6` | (unchanged from today)

The table keys on **mood**; occasion families resolve to a mood via the existing
category→mood data, so adding an occasion needs no new theme code.

### Resolution helper

`theme_for(occasion: str = "", category: str = "") -> dict` returns
`{"bg": hex, "text": hex}`. Resolution order:
1. Map (occasion, category) → mood using the existing
   `categories.py` helpers / `_listing_occasion_key`.
2. Look up mood in the theme table.
3. On any miss → return the default pairing (deep green / cream).

Never raises; an unknown input yields the current default (so nothing regresses).

### Storefront wiring (`listing_preview.py`)

At BUILD time (page generation), resolve each product's default via `theme_for` and
embed ONE `OCCASION_DEFAULT` JS object keyed by **category** → `{bg, text}` (a single
small map, not per-product attributes). When the editor opens a product, its open
routine looks up `OCCASION_DEFAULT[category]` and assigns `SELBG` / `SELTXT` to it
BEFORE any saved design is loaded. Override timing makes the rule automatic: a saved
design (or a manual picker change) is applied AFTER init and carries its own bg/text,
so it overwrites the default — the theme only ever sets the starting point. `SELFONT`
is untouched. If `category` is absent from the map, `SELBG`/`SELTXT` keep today's
default values.

This lives inside the brace-escaped page f-string — literal JS braces `{{`/`}}`,
interpolation `${{...}}`. After editing: `rebuild-site`, then grep the regenerated
`docs/index.html` for the embedded map to confirm it rendered.

## Data flow

```
listing (category / occasion)
        -> mood (categories.py)
        -> theme_for() -> {bg, text}
        -> embedded OCCASION_DEFAULT (build time)
        -> editor SELBG / SELTXT init (only if no saved/changed design)
        -> canvas preview  ──┐
        -> exportPrint() ────┴─> same pixels -> print file
customer override -> existing bg/text pickers -> their choice persists in _fullDesign
```

## Edge cases / rules

- Unknown or ambiguous occasion → current default; no change.
- A saved design or any manual colour change **wins** — never override a customer choice.
- Apparel/mug/calendar: background is the garment/product colour, not `SELBG`; themes
  do not apply (verify the apparel/mug editor path ignores `OCCASION_DEFAULT`).
- All tints are existing palette values — brand-safe, no supplier/marketplace text.

## Testing

- Unit (`theme_for`): each occasion family returns the table's pairing; unknown
  occasion/category returns the default pairing.
- Storefront build: the regenerated page embeds the occasion-default map; a Memorial
  listing resolves to `bg=#f4efe6 / text=#103d2e`; a no-occasion product resolves to
  the default.
- Regression: a saved design's colours are not overridden; no new hex values appear
  outside the existing palette (brand guard).
- Source integrity: `test_source_integrity.py` byte-compiles the new module + page.

## Rollout

Standard branch → PR → merge loop. Storefront change, so after merge: `rebuild-site`,
full suite green, give the UAT link (gate `Jesus`). No config or operator action
required to activate (it's automatic from the listing's occasion).
