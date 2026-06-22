# Joffiels — Go-Live Guide (Self-Hosted, Etsy Checkout, Private Repo)

This is the full path to a **buyable** storefront, hosted on **your own dedicated
computer**, with the **source code private**. Customers browse and personalize on
your site, then check out and pay on **Etsy** (Etsy handles payment, tax, and
fraud; Gelato prints and ships). You never handle card data.

**Recommended low-risk launch order:** start selling on **Etsy only** (Parts 1 +
the "make repo private" step). You host nothing public, so there's no uptime or
security risk — Etsy runs the store. The self-hosted personalizer site (Part 3) is
**optional and can be added later** once you're comfortable; it's a nicer funnel
into the same Etsy listings, not a requirement to sell.

| Step | When | Risk |
|---|---|---|
| **1. Publish on Etsy + connect Gelato** | Now | Very low — Etsy hosts, pays out, handles tax/fraud |
| **Make repo private** | Now | None — protects your code, free |
| **2. Wire `ETSY_SHOP_URL`** | Only if/when you self-host | Low |
| **3. Self-host the personalizer** | Later (optional) | Adds uptime/maintenance — defer until ready |

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

> **Deploying via GitHub Pages? `docs/.nojekyll` is REQUIRED on every deploy.**
> The storefront is a generated static site full of `{`/`}` and `${...}`; GitHub
> Pages' legacy Jekyll build FAILS on it and silently leaves the live site frozen
> on the last good build (this is how "I don't see the new departments" happens —
> a stale build, not a cache). `rebuild-site` now writes `docs/.nojekyll`
> automatically, and `test_build_emits_nojekyll` guards it — do not delete it.
> After any push to the Pages branch, confirm the deploy actually published:
> `gh api repos/<owner>/<repo>/pages/builds/latest` should show `status: built`
> (not `errored`/`building`) on your latest commit.

---

## Part 3 — (OPTIONAL, LATER) Host the personalizer on your dedicated computer

> You do **not** need this to start selling — Etsy is already your store. Add it
> later if you want a branded personalizer that funnels into your Etsy listings.
> The "make repo private" step at the end, however, you can do **now** (it's free).

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

## Rolling back a bad deploy
A deploy can pass the `/health` check yet still behave wrong (e.g. broken routing
or pricing logic). Health-blocking only catches a hard crash — for a "green but
wrong" deploy, roll back immediately:

- **Render (cloud):** Render keeps every prior deploy. Dashboard → the
  `joffiels-server` service → **Deploys** tab → pick the last known-good deploy →
  **Rollback**. The cron services redeploy from the same commit, so revert the
  commit too (below) to keep them aligned.
- **Git (source of truth):** identify the bad commit and revert it, which
  triggers a fresh, correct deploy:
  ```
  git revert <bad-sha>        # or: git revert <oldest-bad>..<newest-bad>
  git push
  ```
  Prefer `git revert` over `reset --hard` so history (and the audit trail) is
  preserved.
- **Self-service (home/NSSM host):** `git checkout <last-good-tag>` (or the
  previous commit), restart the NSSM service, then re-run
  `python -m quoteforge.admin rebuild-site`.
- **Data, not code:** if the issue is data corruption rather than a code bug, use
  the backup/restore runbook in `RESTORE.md` (`restore-all`), which snapshots the
  current DB before restoring so the rollback is itself reversible.

After any rollback, confirm recovery with a smoke check:
`python -m quoteforge.admin healthcheck` and hit `/health` (expect HTTP 200).

## Security recap
- `.env` (keys) is git-ignored and never committed.
- Going private hides all Python business logic (pricing, margins, Gelato costs).
- Cloudflare Tunnel keeps your home IP and ports hidden; traffic is HTTPS.
- You never touch card data — Etsy is the payment processor.
