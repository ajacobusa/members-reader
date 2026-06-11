# Storefront Website Audit (Joffiels UAT)

End-to-end expert audit of `docs/index.html` (the customer-facing storefront), with
findings and the optimizations applied. Re-run the checks after any major rebuild.

## Method
Loaded the built page in a headless browser and measured: render timing, DOM size,
images/lazy-loading, accessibility (alt/labels/headings), console errors, SEO meta,
and asset weight.

## Results

| Dimension | Finding | Status |
|---|---|---|
| **Performance** | DOM interactive ~41ms, 585 DOM nodes, 36/40 images lazy-loaded | ✅ Good |
| **Console** | 0 errors, 0 warnings | ✅ Clean |
| **Headings** | Exactly 1 `<h1>`, logical hierarchy | ✅ Good |
| **Buttons** | 0 buttons missing an accessible label | ✅ Good |
| **Image alt text** | 15 images missing `alt` (gate logo, hero banner, basket thumbnails) | ✅ Fixed → 0 missing |
| **SEO structured data** | No JSON-LD | ✅ Added Organization + WebSite + Product/AggregateOffer |
| **SEO meta** | title, description, OG (5), Twitter (3), canonical, favicon, theme-color, viewport | ✅ Complete |
| **Mobile tap targets** | A few nav links < 34px tall | ✅ Raised to 34px min |
| **Asset weight** | 385 files / 11.9 MB, 230 orphaned (~6 MB) from collapsed designs | ✅ Pruned to 155 files / 5.5 MB |

## Optimizations applied (this audit)
1. **Accessibility:** `alt` text on every image (logo, hero banner, basket thumbnails) — 0 images now lack `alt`.
2. **SEO:** added JSON-LD (`Organization`, `WebSite`, `Product` with `AggregateOffer` $18.99–$256, 46 options) for richer search results.
3. **Mobile:** nav links given a 34px min tap target.
4. **Weight:** pruned 230 orphaned asset files (~6 MB) left over from collapsing the catalog to one design per occasion — no broken references.

## Known / optional (not blocking)
- **Web fonts:** the page loads several Google Font families (Cormorant, Inter, Playfair, Lora, Dancing Script, Oswald, Montserrat) for the personalization font-picker's live preview. `display=swap` is set (no invisible-text flash). If you want a lighter first paint, the picker fonts could be lazy-loaded on editor open — a future enhancement.
- **HTML size (~398 KB):** a single self-contained page with inline CSS/JS + a base64 hero banner. Fine for this use; the banner could be externalized to leverage browser caching if desired.
- This page is UAT/password-gated; for selling, customers are sent to Etsy, so its own SEO is secondary to the Etsy listings.

## How to re-audit
Rebuild (`python -m quoteforge.admin rebuild-site`), then re-check image `alt`,
JSON-LD validity, and orphaned assets (present in `docs/assets` but not referenced
by `docs/index.html`).
