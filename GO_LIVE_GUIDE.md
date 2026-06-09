# Joffiels — Go-Live Guide (Self-Hosted, Etsy Checkout, Private Repo)

This is the full path to a **buyable** storefront, hosted on **your own dedicated
computer**, with the **source code private**. Customers browse and personalize on
your site, then check out and pay on **Etsy** (Etsy handles payment, tax, and
fraud; Gelato prints and ships). You never handle card data.

Do the three parts in order. Parts 1 and 3 can happen in parallel.

---

## Part 1 — Publish your listings on Etsy (you do this)

Everything you need is pre-generated in your launch kit:
`C:/Users/anoop/Desktop/QuoteForge-Output/launch_kit/`

Each `NN_*` folder contains:
- `seo.txt` — the title, tags, description, and which shop section it belongs to
- `gallery/` — the 5 listing images to upload
- `UPLOAD_CHECKLIST.txt` (top level) — a tick-list of every listing

**Steps:**
1. Create your Etsy shop at <https://www.etsy.com/sell> (shop name: **Joffiels**).
2. For **each** listing folder, in Etsy: **Add a listing** →
   - Paste the **title**, **tags**, and **description** from `seo.txt`.
   - Upload the 5 images from that folder's `gallery/`.
   - Set the **section** (named in `seo.txt`).
   - Turn **Personalization ON** (label it "Your name + your message").
   - Set the price ladder from `batch_seo_master.xlsx` (sizes/materials → prices).
   - **Publish.**
3. Connect **Gelato** to Etsy (<https://www.gelato.com>) so orders auto-fulfill,
   and import the matching Gelato products. Keep your **60% net margin** — the
   price ladder already targets this.

> Note: the upload kit uses keyword-rich titles (e.g. "Daughter Graduation Gift")
> because those rank in Etsy search. Your on-site catalog stays generalized
> ("Personalized Graduation Gift") — that's intentional and fine.

When your shop is live, copy your shop URL, e.g. `https://www.etsy.com/shop/Joffiels`.

---

## Part 2 — Point the storefront at your shop (2 minutes)

1. Copy `.env.example` to `.env` (if you haven't already) and set:
   ```
   ETSY_SHOP_URL=https://www.etsy.com/shop/Joffiels
   ```
2. Rebuild the site:
   ```
   python -m quoteforge.admin rebuild-site
   ```
3. Now, after a customer accepts their basket, the site shows a
   **"Continue to checkout →"** button that opens your Etsy shop to pay.

That's the whole funnel: **browse → personalize → review proof → checkout on Etsy.**

---

## Part 3 — Host it on your dedicated computer + make the repo private

### 3a. Run the app (serves the shop AND the personalizer API in one process)
On the dedicated computer (Windows):
```
pip install -e ".[dev]"
pip install waitress
waitress-serve --listen=0.0.0.0:8080 wsgi:app
```
Open <http://localhost:8080/> — you'll see the storefront. Photo upload, Ask Ange,
and save-design all work because the API runs in the same process.

(Linux/VPS alternative: `gunicorn wsgi:app --bind 0.0.0.0:8080 --workers 2`.)

To keep it running 24/7 on Windows, run it as a service with **NSSM**
(<https://nssm.cc>): `nssm install Joffiels` → set the program to your Python's
`waitress-serve` with the args above.

### 3b. Make it reachable to customers (free, secure) — Cloudflare Tunnel
This gives a public **HTTPS** URL without opening ports or exposing your home IP.
1. Install `cloudflared` (<https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>).
2. Quick test tunnel (temporary URL):
   ```
   cloudflared tunnel --url http://localhost:8080
   ```
   It prints a `https://<random>.trycloudflare.com` link — share that to test.
3. Permanent tunnel + your own domain:
   ```
   cloudflared tunnel login
   cloudflared tunnel create joffiels
   cloudflared tunnel route dns joffiels shop.yourdomain.com
   cloudflared tunnel run joffiels
   ```
   Now `https://shop.yourdomain.com` always points to your computer's app.

### 3c. Make the GitHub repo private (now FREE — we no longer use GitHub Pages)
1. <https://github.com/ajacobusa/members-reader/settings> → **Danger Zone** →
   **Change visibility** → **Make private**.
2. You can **turn GitHub Pages off** (Settings → Pages → Source: None) since the
   site is now served from your computer.

Your `repo`-scoped token still pushes/pulls fine after going private. No GitHub
Pro needed.

---

## Daily flow once live
1. Customer personalizes on `https://shop.yourdomain.com`, taps **Continue to
   checkout**, pays on Etsy.
2. Gelato auto-prints and ships; tracking flows back to Etsy.
3. You keep the storefront process running (NSSM service) and push updates with
   `git push`, then `python -m quoteforge.admin rebuild-site` to refresh the page.

## Security recap
- `.env` (keys) is git-ignored and never committed.
- Going private hides all Python business logic (pricing, margins, Gelato costs).
- Cloudflare Tunnel keeps your home IP and ports hidden; traffic is HTTPS.
- You never touch card data — Etsy is the payment processor.
