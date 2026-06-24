# Product-tile photo drop-in sheet

Export each product's photo from your Gelato dashboard, save it with the **exact
filename** below into this `brand/` folder, then run
`python -m quoteforge.admin rebuild-site`. The storefront auto-swaps the tile.
JPG or PNG both work (use the same base name). Missing files just keep the current
default tile — nothing breaks.

> The **live editor already tints colours**, so you only need **one photo per
> product** (a neutral/white shot is ideal) — not one per colour.

---

## 🍵 Mugs
| Product | Save as |
|---|---|
| Classic Ceramic Mug (11oz) | `tile-classic_mug.jpg` |
| Large Ceramic Mug (15oz) | `tile-large_mug.jpg` |
| Colour-Interior Mug (11oz) | `tile-color_mug.jpg` |
| Accent Mug | `tile-accent_mug.jpg` |
| Enamel Camp Mug (12oz) | `tile-enamel_mug.jpg` |
| Stainless Travel Mug (15oz) | `tile-travel_mug.jpg` |
| Large-Capacity Mug (20oz) | `tile-xl_mug.jpg` |

## 📅 Calendars
`tile-wall_cal.jpg` · `tile-desk_cal.jpg` · `tile-family_cal.jpg` ·
`tile-corporate_cal.jpg` · `tile-photo_cal.jpg` · `tile-event_cal.jpg` ·
`tile-promo_cal.jpg`

## 🎁 Branded
`tile-tote.jpg` · `tile-bottle.jpg` · `tile-tumbler.jpg` · `tile-notebook.jpg` ·
`tile-journal.jpg` · `tile-phonecase.jpg`
*(skip `sticker` / `keychain` / `mousepad` — Gelato has no catalog for those.)*

## 👕 Apparel
**Shortcut:** the 3 tiers (Value / Classic / Premium) of a garment are the **same
product** — shoot each garment once and copy the file across its 3 tier-names.

| Garment | Classic (base) | Value | Premium |
|---|---|---|---|
| Men's T-Shirt | `tile-m_tshirt.jpg` | `tile-m_tshirt_value.jpg` | `tile-m_tshirt_premium.jpg` |
| Women's T-Shirt | `tile-w_tshirt.jpg` | `tile-w_tshirt_value.jpg` | `tile-w_tshirt_premium.jpg` |
| Men's Tank Top | `tile-m_tank.jpg` | `tile-m_tank_value.jpg` | `tile-m_tank_premium.jpg` |
| Women's Tank Top | `tile-w_tank.jpg` | `tile-w_tank_value.jpg` | `tile-w_tank_premium.jpg` |
| Men's Long Sleeve | `tile-m_longsleeve.jpg` | `tile-m_longsleeve_value.jpg` | `tile-m_longsleeve_premium.jpg` |
| Women's Long Sleeve | `tile-w_longsleeve.jpg` | `tile-w_longsleeve_value.jpg` | `tile-w_longsleeve_premium.jpg` |
| Men's 3/4 Sleeve | `tile-m_raglan.jpg` | `tile-m_raglan_value.jpg` | `tile-m_raglan_premium.jpg` |
| Women's 3/4 Sleeve | `tile-w_raglan.jpg` | `tile-w_raglan_value.jpg` | `tile-w_raglan_premium.jpg` |
| Men's Polo | `tile-m_polo.jpg` | `tile-m_polo_value.jpg` | `tile-m_polo_premium.jpg` |
| Men's Hoodie | `tile-m_hoodie.jpg` | `tile-m_hoodie_value.jpg` | `tile-m_hoodie_premium.jpg` |
| Women's Hoodie | `tile-w_hoodie.jpg` | `tile-w_hoodie_value.jpg` | `tile-w_hoodie_premium.jpg` |
| Men's Sweatshirt | `tile-m_sweatshirt.jpg` | `tile-m_sweatshirt_value.jpg` | `tile-m_sweatshirt_premium.jpg` |
| Women's Sweatshirt | `tile-w_sweatshirt.jpg` | `tile-w_sweatshirt_value.jpg` | `tile-w_sweatshirt_premium.jpg` |

## 🖼️ Wall Art (works differently — no per-product tiles)
Wall-Art tiles are **generated from the design galleries**, not from a photo per
poster/canvas size. So there is **no `tile-poster_8x10.jpg`** etc. The only photo
Wall Art needs is the department room shot:

| Image | Save as |
|---|---|
| Wall-Art hero / room scene | `wallart-hero.jpg` |

Wall-Art fulfilment UIDs are mapped separately (poster/canvas/framed/acrylic/metal →
real Gelato UIDs) via `python -m quoteforge.admin wallart-automap`; see
[`AUTOMATION_AGENTS.md`](../AUTOMATION_AGENTS.md). Two sizes need a decision: Gelato
has no 8×10 acrylic or metal.

---

## 🔄 3D preview photos (the "View in 3D" selling picture)

Separate from the tiles above: drop a real product photo into
[`brand/mockups/`](mockups/README.md) and that product's **3D preview** upgrades
from the generated body to your buyer's design composited onto the real photo.
Most impactful for the round products (bottle / tumbler / mug). Empty by default —
the generated preview is used until you add one. See
[`brand/mockups/README.md`](mockups/README.md) for filenames + the optional
print-area sidecar.

---

### Two ways to deliver
- **Send me the files** and I'll name, re-host, rebuild, and deploy — and confirm no
  "gelato" URL leaks into the page (the hard rule).
- Or drop them into `brand/` yourself with the names above and I'll rebuild.
