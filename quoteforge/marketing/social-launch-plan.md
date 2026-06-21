# Social launch plan — Joffiels (personalized wall art + apparel)

A practical, low-effort plan for a **new** store. Channel order matters more than
doing everything at once.

## Channel strategy: 2 to start → 1 to amplify → 1 for paid

| Channel | Fit | Role | Effort |
|---|---|---|---|
| **Pinterest** | Best — a *search/shopping* engine; pins sell for months (evergreen); high buying intent | **Core #1 — evergreen traffic & sales** | Low (pin pack is auto-generated) |
| **Instagram** | Strong — visual, gift-able, Reels reach, shoppable, home for proof/UGC | **Core #2 — brand + reach + proof** | Medium |
| **TikTok** | High upside — short video of the "personalize it live" magic; viral potential | **Amplifier — reach & virality** | Higher (frequent video) |
| **Facebook** | Low organic, but the older **gift-buyer** lives here; best as **paid ads** | **Paid engine (Meta Ads = FB + IG)** | Low organic / $ for ads |

**Rollout**
- **Phase 1 (launch):** Pinterest + Instagram.
- **Phase 2 (when you have video capacity):** add TikTok by **reposting the same Reels** (1 video → 3 channels).
- **Phase 3 (with ad budget):** Facebook via **Meta Ads only** (skip organic FB).

**Efficiency unlock:** the on-screen "personalize it live" editor is perfect short-video fuel.
- 🎥 One vertical video (design-with-me / occasion idea / unboxing) → IG Reels + TikTok + Pinterest.
- 🖼️ One set of static product images → Pinterest pins + IG grid (the **pin pack already covers the static side**).

## Pinterest — what's built (in this repo)
- `marketing/pinterest.py` → generates the **pin pack**: 1000×1500 (2:3) pin images + `pins.csv`
  (SEO titles, descriptions+hashtags, board names, **link → the direct store**, keywords).
  - Run: `python -m quoteforge.admin pinterest`
- `marketing/pinterest_publisher.py` → **auto-posts** via the Pinterest API v5 when configured.
  - Run: `python -m quoteforge.admin pinterest-publish` (dry-run unless autopilot + token + board set)
- Scheduled job **"QuoteForge Pinterest Pins"** regenerates + posts on a cadence (when live).
- **Pin links go to the live store** via `STORE_URL`: the **current Etsy shop** today;
  set `STORE_URL=https://joffiels.com` at the direct-store launch to flip them.

## Pinterest go-live checklist
1. Create a free **Pinterest *business* account** → pinterest.com/business/create.
2. **Claim your website** (`joffiels.com`) in Settings (verified pins + analytics).
3. Create a **developer app** at developers.pinterest.com → access token with scopes
   `pins:write`, `boards:read`, `boards:write`.
4. Create **boards**: *Personalized Wall Art*, *Custom Apparel Gifts*, + occasion boards
   (Anniversary, Wedding, For Mom, For Dad, Memorial, New Baby, Graduation, Just Because) → copy a **board id**.
5. Set env vars (Render env group / `.env`):
   - `STORE_URL` — **leave unset today** (pins link to the current Etsy shop); set to
     `https://joffiels.com` when the **direct store** launches.
   - `PINTEREST_ACCESS_TOKEN=…`
   - `PINTEREST_BOARD_ID=…`
6. **Dry-run → live:** `python -m quoteforge.admin pinterest-publish` (verify), then
   `PINTEREST_AUTOPILOT=true` — the scheduled job posts automatically.

## Two-week launch content calendar (Pinterest + Instagram)
Principle: 1 video → 3 places; static designs → pins + grid. ~1 post/day; front-load Pinterest.

| Day | Pinterest (3–5 evergreen pins/day from the pack) | Instagram |
|---|---|---|
| Mon | Anniversary designs → Anniversary board | Reel: "Watch your words become art" (live editor) |
| Tue | For Mom / For Dad designs | Carousel: 5 occasion ideas |
| Wed | Wedding + New Baby designs | Story: behind-the-scenes / poll |
| Thu | Apparel: tee / hoodie occasion mockups | Reel: "Design a custom hoodie in 30s" |
| Fri | Memorial / Just Because (emotional angle) | "Proof before it prints" reassurance post |
| Sat | Gallery-wall / gift-set pins | Reel: unboxing / "the moment they open it" |
| Sun | Re-pin top performers to occasion boards | Story: this week's best design + link |
| **Week 2** | Repeat; double down on the pins with the most **saves/clicks** | Add **TikTok** by reposting week-1 Reels |

**Cadence reality:** Pinterest = batch-schedule ~20 pins/week (low effort). Instagram = 3 Reels + 2 static/week.
Don't touch Facebook organic — save FB for paid Meta ads in month 2+.

## Today vs. launch
- **Today:** the store runs on **Etsy**. Pinterest pins link there (no `STORE_URL` needed).
  You can connect Pinterest + flip `PINTEREST_AUTOPILOT=true` now to drive traffic to the Etsy shop.
- **At direct-store launch:** point **`joffiels.com`** at the live storefront (the GitHub Pages
  preview is gated/`noindex` — not a public link), then set `STORE_URL=https://joffiels.com`
  to flip every marketing link to the new site in one switch.
