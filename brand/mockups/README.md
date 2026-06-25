# Real Gelato product photos — drop sheet (exact-match previews)

We resell Gelato products, so the customization preview should look like the
**actual Gelato product**. Drop the real Gelato photo for a product in here and the
editor + preview composite the customer's design **onto that exact photo**. The
image is **re-hosted locally** on build, so the published page never contains the
word "gelato" (the hard no-supplier-leak rule still holds — checked on every build).

> Until a photo is added, a product uses a clean generated preview (flat products
> show a recognizable silhouette; mugs/bottles show the print field + spin). Adding
> a photo here **upgrades that product to the real picture** — nothing breaks while
> it's empty.

## What to export from Gelato

For each product, in your **Gelato dashboard → the product → Mockups / product
image**, export **one clean, front-on shot on a white/neutral background** with
**no sample design on it** (a blank product). PNG or JPG. Then save it here with the
exact filename below and run `python -m quoteforge.admin rebuild-site`
(or just send me the files and I'll name, re-host, tune, and rebuild).

> **Blank is important.** Use the *plain* product shot — not a marketing image that
> already has a sample design printed on it (that would show the sample, not the
> customer's art).

## Filenames (`<product_id>.png`)

**🍵 Mugs** — `classic_mug` · `large_mug` · `color_mug` · `accent_mug` ·
`enamel_mug` · `travel_mug` · `xl_mug`

**🎁 Branded** — `tote` · `bottle` · `tumbler` · `mousepad` · `notebook` ·
`journal` · `sticker` · `phonecase` · `keychain`

**📅 Calendars** — `wall_cal` · `desk_cal` · `family_cal` · `corporate_cal` ·
`photo_cal` · `event_cal` · `promo_cal`

**👕 Apparel** — by `garment_id` (a colour-neutral / white shot, one per garment):
`m_tshirt` · `w_tshirt` · `m_tank` · `w_tank` · `m_longsleeve` · `w_longsleeve` ·
`m_raglan` · `w_raglan` · `m_polo` · `m_hoodie` · `w_hoodie` · `m_sweatshirt` ·
`w_sweatshirt`

## Optional: tell it where the print sits (`<product_id>.json`)

I'll tune these for you once your photos are in, but for reference — a sidecar next
to the image marks the print rectangle as fractions `0–1` of the photo:

```json
{ "area": [0.30, 0.34, 0.40, 0.34], "cyl": true, "span": 1.9 }
```
- `area` = `[x, y, width, height]` of the print zone on the photo.
- `cyl` = `true` for round products (mug / bottle / tumbler) so the design wraps on
  the barrel; `false` for flat products (tote / phone case / tee …).
- `span` = how much of the barrel front is visible (radians; ~1.9 default).

With no sidecar, sensible defaults are used (centred print; `cyl` inferred from the
product name).

## The simplest hand-off

**Send me the exported photos** (or drop them in this folder). I'll re-host them,
set the print-area geometry per product so the design lands exactly right, rebuild,
and give you the UAT link — and confirm no "gelato" leaks into the page.
