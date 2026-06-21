# Apparel Layout Studio — design spec

Date: 2026-06-20
Owner: Joffiels (QuoteForge apparel editor)
Status: approved design → implementation planning

## Problem

When a customer uploads a logo / graphic for a T-shirt, the editor today places a
single text block + the image with manual drag/size. Most customers can't compose
a professional layout. They want curated, professional arrangements — especially
**curved wording around the image** (badge style, e.g. "CAMP WINDERMERE … LAKE
MARTIN 2025" arched above/below a graphic) — and the ability to try many looks.

## Goal

Add a **Layout Studio** to the apparel design editor: the customer uploads their
graphic, types their words into structured slots, picks one of **12 professional
layout presets**, and the editor auto-arranges a print-ready composition. Every
result stays tweakable (move/resize/recolour/font), front and back keep their
independent designs, and nothing prints off the garment.

This is a storefront-only change in `quoteforge/etsy/listing_preview.py` (the page
generator). No backend/order-schema changes beyond carrying the structured design
data through the existing order payload.

## Non-goals (v1)

- True multi-image upload — only **Photo Collage (J)** wants it; v1 renders collage
  as ONE uploaded image inside a decorative multi-frame. Multi-image is a fast-follow.
- AI auto-layout suggestions. The presets ARE the expertise.
- New supplier/print-pipeline work. Layouts render within the existing print frame.

## Customer flow

1. Switch to an apparel garment, open the design editor (existing).
2. Upload a graphic (existing photo upload) and/or type words.
3. Open the **Layout** gallery (new) — 12 thumbnails (the styles below).
4. Pick a layout → the editor auto-arranges image + words into that composition.
5. Only the **text slots that layout uses** are shown for editing.
6. Tweak anything (nudge/resize/recolour/font/decoration) — optional.
7. Design the back independently (existing front/back spin).
8. Review in the final proof (existing; front/back rotate already shipped) → approve.

A **Freeform** option (default) preserves today's single-block behaviour, so the
new system is additive and never blocks the current flow.

## The 12 layouts

| Key | Name | Text slots used | Signature |
|----|------|-----------------|-----------|
| A | Circular Badge | Top arc, Bottom arc | Words arc around the logo + ring border |
| B | Vintage Emblem | Headline, Secondary, Tagline | Decorative borders; Secondary renders inside a banner ribbon |
| C | Modern Minimalist | Headline, Tagline | Small logo, wide-spaced caps, restraint |
| D | Oversized Streetwear | Headline, Secondary | Huge centre graphic, bold overlapping type |
| E | Vertical Stack | Headline, Secondary, Tagline | Text · logo · text, strong hierarchy |
| F | Horizontal Banner | Headline, Secondary | Logo + words side-by-side |
| G | Left-Chest Logo | Headline | Small simplified mark, chest placement |
| H | Back Print | Top arc, Tagline | Big statement graphic, event-style |
| I | Wraparound | Top arc (full ring) | Words flow in a full 360° ring around the logo |
| J | Photo Collage | Headline | Framed image(s) + layered type (single image v1) |
| K | Adventure Badge | Top arc, Bottom arc | Shield/hexagon, est. date, location |
| L | Luxury Monogram | Monogram, Headline | Elegant interlocked initials, serif |

The owner-supplied TEXT PLACEMENT RULES are encoded in each layout's slot config:
1–3 words → a single dominant headline slot; 4–8 → headline + secondary; 9–20 →
multi-level (headline + secondary + tagline / arcs); 20+ → the layout caps slot
length and the editor warns (readability at print size).

## Architecture

All within the page f-string in `listing_preview.py` (brace-escaped: `{{ }}`
literal, `${{ }}` JS interpolation). Reuses the existing canvas (`#mcanvas`),
photo (`PHOTO`), per-side state (`SIDES`), and proof/rotate pipeline unchanged.

### 1. Text slots (replaces single text box for apparel layouts)

A small fixed set of named slots; each layout uses a subset:

- `headline` — dominant words (maps to today's `#mtext` for back-compat)
- `secondary` — sub-headline
- `arcTop` — curved wording above the logo
- `arcBottom` — curved wording below the logo
- `tagline` — small line (est. / location / date)
- `monogram` — 1–3 initials (style L only)

State: `SLOTS = {{headline, secondary, arcTop, arcBottom, tagline, monogram}}`
(strings). The editor renders inputs only for the active layout's slots, each with
its own char cap. `headline` stays wired to the current `#mtext` so existing tests
and the Freeform path keep working.

### 2. Curved-text engine

`drawArcText(ctx, text, cx, cy, radius, midAngleDeg, sweepDir, font, size, color, opts)`
— positions each glyph along a circle by advancing angle = glyphWidth/radius.
`sweepDir = +1` for a top arc (clockwise, baseline outward) and `-1` for a bottom
arc (counter-clockwise, glyphs flipped 180° so they read upright). Centred on
`midAngleDeg`. Letter-spacing + uppercasing per layout default.

### 3. Layout definitions (data-driven)

`const LAYOUTS = [...]`, one entry per A–L:

```
{{ key, name,
   slots: [{{slot, kind:'arc'|'line', cx,cy, r?, midAngle?, sweep?,
            x?,y?, align, weight, font, caps, maxChars}}],
   logo: {{cx, cy, scale, frame?:'ring'|'doublering'|'border'|'shield'|'hexagon'
           |'monogram'|'collage'|'none'}},
   decor: ['ring'|'banner'|'waves'|'rule'|'stars'|'laurel'...],
   defaultFont, thumb: '<svg…>' }}
```

`drawArt()` gains an apparel **layout branch**: if `CURLAYOUT` is set and not
`freeform`, it renders decorations → logo (placed/scaled per def, clipped to any
frame) → each text slot (arc via `drawArcText`, else wrapped line) using the
layout's hierarchy, instead of the current single-block path. The existing
free-form rendering remains the `freeform` branch.

### 4. Decorative elements

Reusable canvas helpers, data-driven per layout: `_decRing`, `_decDoubleRing`,
`_decBorder`, `_decBanner`, `_decWaves`, `_decRule`, `_decStars`, `_decShield`,
`_decHexagon`, `_decMonogramFrame`, `_decCollage`. Drawn in the layout's ink
colour. Customers can toggle a layout's optional decor (e.g. the waves divider).

### 5. Typography

Add display fonts to `FONTS`: a bold condensed (`Bebas Neue` and/or `Oswald`) for
streetwear/athletic looks; keep `Cormorant Garamond` for elegant/monogram. Fonts
loaded via the existing Google Fonts `<link>`. Each layout sets a default font;
the customer can override with the existing font picker. Existing auto-contrast
(white ink on dark shirts) is reused for every slot.

### 6. Gallery UI

A new "Layout" panel in the editor's left/controls column: a scrollable grid of 12
SVG thumbnails (built once, reused from the design mock). Clicking sets
`CURLAYOUT`, swaps the visible slot inputs, and redraws. A "Freeform" tile is first
and selected by default. Keyboard-operable (matches existing fchip a11y pattern).

### 7. Persistence & order payload

`CURLAYOUT` + `SLOTS` are added to `_captureSide()` / `_restoreSide()` (so each
side remembers its layout + slot text) and to the cart-item / order payload
alongside the existing `wording`. `wording` is set to a readable concatenation of
the active slots so existing summaries/printers still get text. The proof composer
and front/back rotate (already shipped) work unchanged — they composite whatever
`drawArt()` renders.

## Print-safety

Every layout renders inside the existing movable print bound (`_placeBoundMock` /
the design FRAME). Arc radii and slot positions are expressed as fractions of that
bound, so the whole composition scales with the frame and never lands on the
collar or off the garment. Minimum on-garment font sizes enforced per slot so text
stays legible at print size (the typography rule).

## Customer-facing copy rules (hard constraints)

- No supplier/marketplace name anywhere (Gelato/Printify/Etsy) — incl. JS
  identifiers/comments. Layout names are generic design terms.
- Layout help text stays about design, not production.

## Testing

String/integration tests in `quoteforge_tests/test_apparel_storefront.py`:
- `LAYOUTS` defines 12 entries; gallery renders 12 thumbnails + a Freeform tile.
- `drawArcText` present and used by the arc layouts (A, H, I, K).
- Each layout's declared slots have inputs wired; slot inputs swap on layout change.
- Added display fonts present in `FONTS` and in the font `<link>`.
- `CURLAYOUT` + `SLOTS` captured per side and carried into the order payload.
- No supplier/marketplace leak (extends existing `test_customer_copy_no_leak`).
- Freeform default keeps current single-block behaviour (back-compat).

Live verification via the Claude_Preview MCP: open the editor, pick representative
layouts (Circular Badge, Adventure Badge, Wraparound, Vertical Stack, Streetwear),
confirm arcs/positions render and recolour, and the front/back rotate + proof still
compose correctly. Then full suite green + safe-deploy loop (branch → PR → merge →
backup → UAT).

## Rollout

All 12 ship in one release (owner's choice). Implementation is incremental
internally: (1) arc engine + slots + Freeform/Circular Badge, (2) remaining
data-driven layouts + decorations, (3) gallery UI + persistence + tests — but
merged together. UAT link provided after merge (gate password `Jesus`).

## Risks & mitigations

- **Taste/revert risk** (a heavy picker was reverted before): mitigated by showing
  the design mock up front (done) and keeping Freeform as the untouched default.
- **Editor file size**: `listing_preview.py` is already large; layouts are
  data-driven to limit new surface. If the layout data + helpers grow unwieldy,
  factor the LAYOUTS table + decor helpers into a clearly-commented section.
- **Glyph metrics for arcs**: measured via `ctx.measureText` per glyph; tested
  visually on the representative arcs.
- **Collage multi-image**: deferred; single-image decorative frame in v1.
