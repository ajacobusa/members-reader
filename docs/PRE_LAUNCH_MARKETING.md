# Pre-Launch Marketing — Email Capture, Pinterest, Analytics

Three nice-to-haves that meaningfully lift launch results. All are wired into
the CLI; the only manual steps are creating the external accounts and pasting
the IDs/URLs into `.env`.

## 1. Email capture — build an audience you own
Set your signup form URL, then generate the kit:
```bash
# .env
SIGNUP_URL=https://your-list.mailerlite.com/...
python -m quoteforge.admin email-capture
```
Produces (in `QuoteForge-Output/email_capture/`):
- **signup_qr.png** — QR code for package inserts / business cards (needs
  `pip install qrcode[pil]`; otherwise a hosted-QR URL is written instead).
- **shop_announcement.txt** — paste into Etsy → Shop announcement (with CTA).
- **linktree.txt** — ready-made Linktree blocks.
- **signup_snippet.html** — drop-in email form for any website.
- **thankyou_insert.txt** — printable insert card copy.

Captured emails live in the `subscribers` table:
```bash
python -m quoteforge.admin subscribers              # list
python -m quoteforge.admin subscribers add a@b.com website
```

## 2. Pinterest — highest-ROI POD traffic
```bash
python -m quoteforge.admin pinterest          # all listings
python -m quoteforge.admin pinterest 1 5 7    # specific ones
```
Generates 1000×1500 (2:3) pins for each product + evergreen **gift-guide**,
**seasonal**, and **home-decor** pins, plus `pins.csv` (SEO title, description
with hashtags, board, destination link). Bulk-upload the images and paste the
copy from the CSV (or feed it to the Pinterest API later).

## 3. Analytics
- **Etsy Shop Stats** — no code; enable inside Etsy (Shop Manager → Stats).
- **Google Analytics** + **Microsoft Clarity** — set the IDs and they're
  auto-injected into the GitHub Pages shop-home page on the next build:
```bash
# .env
GA_MEASUREMENT_ID=G-XXXXXXX
CLARITY_PROJECT_ID=xxxxxxxxxx
python -c "from quoteforge.etsy.listing_preview import build_shop_home; \
from pathlib import Path; build_shop_home(out_path=Path('docs/index.html'))"
```
Both are no-ops when blank, so nothing leaks into the page until you opt in.
