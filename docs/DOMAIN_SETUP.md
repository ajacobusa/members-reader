# Joffiels.com — domain + go-live game plan

**Decision:** Joffiels.com is a **free brand/showcase site (GitHub Pages)** whose
buttons send buyers to **Etsy** (where payment + fulfillment happen).

---

## Step 1 — Buy the domain (GoDaddy, ~$15/yr)
Search "joffiels.com" (or .shop/.store/.art if .com is taken) and buy it.
Skip the upsells (privacy is usually free; you don't need their hosting/email/
website builder — we host on GitHub Pages for free).

## Step 2 — Tell me the exact domain
Once purchased, give me the exact name and I'll add a **`CNAME` file** to `docs/`
and reconfigure the build so the site serves on your domain.

## Step 3 — Point DNS at GitHub Pages (in GoDaddy → My Domains → DNS)
Add these records (GitHub Pages IPs for the apex domain):

| Type | Name | Value | TTL |
|---|---|---|---|
| A | @ | 185.199.108.153 | 600 |
| A | @ | 185.199.109.153 | 600 |
| A | @ | 185.199.110.153 | 600 |
| A | @ | 185.199.111.153 | 600 |
| CNAME | www | ajacobusa.github.io | 600 |

(Delete any default GoDaddy "Parked"/forwarding A record first.)

## Step 4 — Enable it on GitHub
Repo → **Settings → Pages → Custom domain** → enter `joffiels.com` → Save →
tick **Enforce HTTPS** (after the cert provisions, ~minutes to an hour).

## Step 5 — Flip the site from "UAT" to "public" (I do this in code)
Before it's public-facing I'll:
- **Remove the "Jesus" password gate** (it's only for private review).
- Replace "sample preview for review" copy with real shop copy.
- Add **"Personalize on Etsy"** buttons linking to your Etsy shop/listings
  (needs your Etsy shop URL → set `ETSY_SHOP_URL`).
- Keep Ask Ange, live previews, reviews, order-by banner, etc.

## Step 6 (optional, later) — live Ask Ange + webhooks
If you host the server (Render, ~$7/mo, see `DEPLOY.md`), point
`api.joffiels.com` at it (CNAME to the Render URL) and set
`ASK_ANGE_API_URL=https://api.joffiels.com/ask` for full Claude answers.

---

## What stays the same
- **Etsy** remains the cash register (cart, checkout, payment, Purchase
  Protection). Joffiels.com drives traffic + trust to it.
- Hosting cost: **$0** (GitHub Pages). Only the domain (~$15/yr) is required.

## Heads-up / gotchas
- DNS changes can take 15 min–24 h to propagate.
- A domain doesn't add checkout — selling still happens on Etsy (by design).
- Don't buy GoDaddy hosting/website-builder; you don't need it.
- Keep `TEST_MODE=true` until the physical Gelato sample is approved.
