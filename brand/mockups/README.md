# Product preview — real-photo override (optional)

The customization preview (editor + the inline **"Spin your product"** view) shows
the buyer's design **on the real product photo**. It already pulls those photos
**automatically** from the same pipeline the grid tiles use — the
`tile-<product_id>.jpg` files the `product-photos` agent downloads (apparel uses
the per-colour / front+back photos). So you normally do **nothing** here.

**This folder is only an override** — use it when you want to (a) supply a
different photo just for the preview, or (b) fine-tune *where* the print sits on a
photo via the geometry sidecar (below). When empty, the auto pipeline + a clean
generated fallback are used, so nothing ever breaks.

## How to override one

1. Export a clean, front-on product photo (white/neutral background is ideal) —
   export it once from your print-partner mockup studio, or use any real product
   shot.
2. Save it here as **`<product_id>.png`** or `.jpg` (the product ids are the same
   ones used by the tile photos — see the table below).
3. *(Optional but recommended)* add a sidecar **`<product_id>.json`** that marks
   where the print sits on the photo, as fractions `0–1` of the image:

   ```json
   { "area": [0.30, 0.34, 0.40, 0.34], "cyl": true, "span": 1.9 }
   ```
   - `area` = `[x, y, width, height]` of the print rectangle on the photo.
   - `cyl` = `true` for round products (mug / bottle / tumbler) so the design
     wraps on the barrel; `false` for flat products (tee / poster / tote).
   - `span` = how much of the barrel front is visible (radians; ~1.9 is a good
     default). Ignored when `cyl:false`.

   With no sidecar, sensible defaults are used (a centred print, and `cyl` inferred
   from the product name).
4. Run `python -m quoteforge.admin rebuild-site`.

## Product ids (key cylindrical ones first)

| Product | Save as |
|---|---|
| Insulated Stainless Water Bottle | `bottle.png` |
| Stainless Tumbler | `tumbler.png` |
| Classic Ceramic Mug (11oz) | `classic_mug.png` |
| Large Ceramic Mug (15oz) | `large_mug.png` |
| Enamel Camp Mug (12oz) | `enamel_mug.png` |
| Organic Cotton Tote Bag | `tote.png` |
| Hardcover Journal | `journal.png` |

Apparel garments and other products use the **same ids** as their tile photos —
see [`../PRODUCT_PHOTO_FILENAMES.md`](../PRODUCT_PHOTO_FILENAMES.md).

> **Customer-safe:** only the image bytes + geometry are published to the
> storefront — never a supplier or marketplace name. The page is checked for that
> on every build.
