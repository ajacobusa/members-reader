# QuoteForge Deployment Guide

This guide covers running QuoteForge locally and deploying the webhook server
and web monitor to the cloud so your automation runs 24/7 without your PC on.

---

## TEST_MODE — Always Start Here

QuoteForge ships with `TEST_MODE=true`. In test mode the pipeline generates
mock quotes and mock Gelato orders **without spending money on real API calls**.

Keep `TEST_MODE=true` until a full test order has passed end-to-end. Then flip it:

```env
# In your .env file
TEST_MODE=false
```

---

## Local Testing

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install flask streamlit pandas      # automation extras

# 2. Configure
cp .env.example .env        # then edit .env with your keys

# 3. Initialize the database
python -c "from quoteforge.db.database import init_db; init_db()"

# 4. Run the webhook server (terminal 1)
python -m quoteforge.automation.webhook_server

# 5. Run the web monitor (terminal 2)
streamlit run quoteforge/web_monitor.py

# 6. Or run the desktop app
python quoteforge/main.py
```

---

## Deploy Webhook Server to Render (free tier)

Render keeps your webhook endpoint online 24/7 so Make.com can reach it
even when your computer is off.

1. Push this project to a **private** GitHub repo (never commit `.env`).
2. Go to [render.com](https://render.com) → New → Web Service.
3. Connect your GitHub repo.
4. Configure:
   - **Build command:** `pip install -r requirements.txt flask`
   - **Start command:** `python -m quoteforge.automation.webhook_server`
   - **Note:** the server binds to `0.0.0.0:5050`. On Render set the port via
     the `PORT` env var, or run with gunicorn:
     `gunicorn -b 0.0.0.0:$PORT "quoteforge.automation.webhook_server:app"`
5. Add environment variables (from `.env.example`) in the Render dashboard:
   - `TEST_MODE`, `ANTHROPIC_API_KEY`, `GELATO_API_KEY`, `ETSY_WEBHOOK_SECRET`, etc.
6. Deploy. Copy your Render URL: `https://your-app.onrender.com`
7. In Make.com, point the HTTP module at `https://your-app.onrender.com/order`.

> Render's free tier sleeps after inactivity. For always-on, use the $7/mo
> Starter plan, or keep your local machine + ngrok for low volume.

---

## Deploy Web Monitor to Streamlit Cloud (free)

1. Go to [share.streamlit.io](https://share.streamlit.io).
2. Connect your GitHub repo.
3. Set main file: `quoteforge/web_monitor.py`.
4. Add secrets (same keys as `.env`) in the Streamlit Cloud secrets panel.
5. Deploy. Share the URL with your VAs — they can monitor orders from a phone.

> Note: the SQLite database lives on the server's local disk. For a shared
> live dashboard across machines, point both the webhook server and the
> monitor at the same database (e.g. a mounted volume) or use Airtable as the
> shared source of truth.

---

## Security Checklist Before Going Live

- [ ] `.env` is in `.gitignore` (never commit secrets)
- [ ] `ETSY_WEBHOOK_SECRET` is set — webhook signature verification is active
- [ ] `TEST_MODE=false` only after a successful test order
- [ ] `PIPELINE_AUTO_APPROVE_PROOF=false` for custom personalized orders
      (always review personalized messages before they print)
- [ ] Render/Streamlit environment variables are set, not hardcoded
- [ ] First real order placed and verified end-to-end before scaling ads
