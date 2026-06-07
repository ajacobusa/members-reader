# Hosting the server 24/7 (webhook + Ask Ange + tracking)

You have **two ways** to run the automation. Pick one:

| | A) Your PC (free, today) | B) Cloud host (24/7) |
|---|---|---|
| Order intake | scheduled `poll-etsy` (every 10 min) | live `/order` webhook **and** cron poll |
| Ask Ange `/ask` (full Claude) | not reachable from the public site | live endpoint the site calls |
| Tracking / delivery | scheduled `track-orders` | cron `track-orders` |
| Cost | $0 (PC must be on) | ~$7/mo (Render Starter) + |

**You only need cloud hosting for:** the live **Ask Ange** answers on the public
site, inbound Etsy/Make webhooks, and running when your PC is off. Everything
else already works on your PC via `install-schedule`.

---

## Option A — Your PC (already built)
```
python -m quoteforge.admin install-schedule   # run as Administrator
```
Registers all jobs in Windows Task Scheduler (poll-etsy, track-orders, ledger,
briefing, backups, etc.). Runs whenever the PC is on. Nothing else to do.

---

## Option B — Render.com (recommended cloud, ~10 min)
A `render.yaml` blueprint is included (web service + persistent disk + cron jobs).

1. Push this repo to GitHub (already connected).
2. Render → **New + → Blueprint** → pick this repo. It reads `render.yaml`.
3. In the dashboard, set the **secret** env vars (marked `sync:false`):
   `ANTHROPIC_API_KEY`, `GELATO_API_KEY`, `ETSY_API_KEY`, `ETSY_OAUTH_TOKEN`,
   `ETSY_WEBHOOK_SECRET` (+ any others from `.env.example`).
4. Deploy. You get a URL like `https://joffiels-server.onrender.com`.
5. Verify: open `https://.../health` → should return `{"status":"ok"}`.
6. **Wire Ask Ange to it:** set `ASK_ANGE_API_URL=https://.../ask` and run
   `rebuild-site` so the on-page bot gives full Claude answers.
7. (Optional) Point an Etsy/Make webhook at `https://.../order`.

The blueprint mounts a **persistent disk at `/data`** and sets `OUTPUT_DIR=/data`
so the SQLite DB + assets survive redeploys, and runs cron jobs for `poll-etsy`,
`track-orders`, and a daily ops batch.

### Other hosts
- **Railway / Fly.io / Heroku:** use the included `Procfile`
  (`web: gunicorn wsgi:app ...`). Set a persistent volume + `OUTPUT_DIR`.
- **Any VPS (Docker):**
  ```
  docker build -t joffiels .
  docker run -d -p 80:5050 -e OUTPUT_DIR=/data -v /srv/joffiels:/data \
    -e ANTHROPIC_API_KEY=... -e GELATO_API_KEY=... joffiels
  ```
  Add host `cron` entries for `poll-etsy` / `track-orders` / daily jobs.

---

## Critical notes
- **Persistent storage:** always set `OUTPUT_DIR` to a mounted disk/volume on a
  host - otherwise the SQLite DB resets on every redeploy.
- **Secrets:** never commit real keys; set them in the host dashboard. `.env`
  stays gitignored.
- **TEST_MODE:** keep `true` until the physical Gelato sample is approved, then
  set `false` to go live.
- **Backups:** the nightly `backup-all` already pushes to GitHub; on a host,
  also rely on the persistent disk + (optional) `BACKUP_TO_DRIVE`.
