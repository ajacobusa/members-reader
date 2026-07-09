# Photo provenance — installed real product photos

Every installed photo below was collected from an OFFICIAL Gelato-published
public asset (no scraping, no fabrication), visually QA'd (blank base, no
printed design, no stranger product), and validated by
`admin real-photos install` (decode + >=400px/side + manifest naming).

Source hosts (both public, unauthenticated GETs, verified 200):
- `S3` = s3.eu-west-1.amazonaws.com/gelato-api-live/preflight/preview/ — the
  dashboard product gallery's own flat "editor" blanks; the dotted product
  model in the path was read off the LIVE product page for that exact product
  (or construct-and-verified against it), mirroring our UID grammar.
- `CDN` = cdn.sanity.io/images/69l8b8xl/production/ — Gelato dashboard product
  gallery stills (owner-session assisted collection, 2026-07).

| product_id   | source | path under host                                                        | QA |
|--------------|--------|------------------------------------------------------------------------|----|
| m_tshirt     | S3     | t-shirt.crewneck.unisex.classic.gildan.64000/editor/front/white-1000x1000.webp | blank flat front ✓ |
| w_tshirt     | S3     | t-shirt.crewneck.womens.classic.gildan.64000l/editor/front/white-1000x1000.webp | blank flat front ✓ |
| m_longsleeve | S3     | t-shirt.longsleeve-crew.unisex.classic/editor/front/white-1000x1000.webp | blank flat front ✓ |
| m_tank       | S3     | t-shirt.tank-top.unisex.prm/editor/front/white-1000x1000.webp           | blank flat front ✓ |
| w_tank       | S3     | t-shirt.tank-top.womens.performance/editor/front/white-1000x1000.webp   | blank flat front ✓ |
| m_hoodie     | S3     | hoodie.pullover.unisex.classic.gildan.18500/editor/front/white-1000x1000.webp | blank flat front ✓ |
| w_hoodie     | S3     | hoodie.pullover.womens.prm/editor/front/white-1000x1000.webp            | blank flat front ✓ |
| m_sweatshirt | S3     | sweatshirt.crewneck.unisex.classic.gildan.18000/editor/front/white-1000x1000.webp | blank flat front ✓ |
| tote         | CDN    | f9b896ce3e076903147643a9c01047502740382d-2245x1587.jpg (Classic Tote Bag gallery) | blank flat front ✓ |
| classic_mug  | CDN    | 88ba70db2964147c95731f292a5dc73bb8993ead-2000x2000.jpg                  | blank ✓ |
| enamel_mug   | CDN    | e0bba8a4b4c495f738619eccd8c5599ee188122b-1000x1000.jpg                  | blank ✓ |
| large_mug    | CDN    | 9f2b3a0b047f4c7d9a091420068924b9a9d67c1d-1000x1000.png                  | blank ✓ |
| travel_mug   | CDN    | 7724b7f4bf78cc1873a548e980d84730fc394b04-512x520.png                    | blank ✓ (first pick rejected: printed design) |
| xl_mug       | CDN    | d60a54788ebbf07be028cd4b9fe4bb7c150ae9fb-1000x1000.png                  | blank ✓ |

Rejected during QA (never installed / removed): printed-design tote (f3990745),
"Donut Worry" tote (df6ebcbc), wall-art posters mis-grabbed from stale SPA DOM
(5fcad60b, 822b872a), size-guide line drawings (bc649729, 9c112882), botanical
travel mug. Lesson locked: extraction must be VISIBLE-GALLERY-ONLY — offscreen
DOM nodes on the dashboard SPA contain other products' images.

Steady state: once Etsy OAuth + GELATO_STORE_ID are active, the daily
`real-photos collect` job replaces these with Gelato-published Etsy listing
images (the no-human loop); these files remain the approved owner-asset
fallback.
