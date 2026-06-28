# Daily Sales Report Email — Setup

A daily email to **joffielsc@gmail.com** with order counts, follow-ups needed,
and **demand-based tier upgrade alerts**. Runs unattended via Windows Task
Scheduler — no need to keep any app open.

> **Note on "auto-upgrade":** the report *detects* when order volume approaches
> a service's plan limit and tells you to upgrade, with the exact plan + price.
> It does **not** auto-charge your card — flipping a paid subscription is your
> click, by design. Reverting is also yours (`RENDERER=local`).

---

## Step 1 — Gmail App Password

1. Enable 2-Step Verification: myaccount.google.com → Security
2. Security → **App passwords** → create one named "QuoteForge"
3. Copy the 16-character password.

Add to `.env`:
```env
GMAIL_ADDRESS=your_sending_gmail@gmail.com
GMAIL_APP_PASSWORD=the_16_char_app_password
REPORT_RECIPIENT=joffielsc@gmail.com
```

## Step 2 — Test it once

```powershell
python -m quoteforge.admin email-report
```
You should get the email within a minute. If it prints "not sent", the Gmail
credentials aren't set yet.

## Step 3 — Schedule EVERYTHING with one command

You no longer create tasks by hand. A single command registers all eight
recurring jobs (daily/weekly/monthly/yearly reports, backup, health check,
monthly campaign, weekly sales actions) in Windows Task Scheduler:

```powershell
# Preview exactly what will be created (changes nothing):
python -m quoteforge.admin install-schedule --dry-run

# Create them all (run in an Administrator terminal):
python -m quoteforge.admin install-schedule

# Remove them all later if you ever need to:
python -m quoteforge.admin install-schedule --remove
```

The job definitions live in one place (`quoteforge/automation/scheduler.py`),
and the health check reads that **same** list — so the jobs that get created and
the jobs that get monitored can never fall out of sync.

Verify they registered and are enabled at any time:
```powershell
python -m quoteforge.admin healthcheck
```
The `Scheduled Jobs` check turns to `[OK] 8 jobs registered and enabled` once
they're installed; it reports anything `missing` or `disabled` otherwise (and
emails you an alert if a job ever disappears).

## Daily self-healing maintenance agent

One of the scheduled jobs (`QuoteForge Daily Maintenance`, 6:00 AM) is an agent
that keeps the infrastructure running without you. Each morning it:

1. **Checks** the DB, storage, backups, scheduled jobs, and stuck orders.
2. **Fixes** the operational problems it's safe to fix unattended:
   - re-installs any scheduled job that went missing or got disabled,
   - takes a fresh backup if the latest one is stale,
   - runs `VACUUM` + WAL checkpoint + integrity check to keep queries fast.
3. **Measures** performance (DB size, query latency, space reclaimed).
4. **Suggests** enhancements based on live numbers (errored orders, when to
   scale listings, when to review tier capacity).
5. **Emails** you a single digest of everything it did and recommends.

Run it manually any time:
```powershell
python -m quoteforge.admin maintenance          # heal + print digest
python -m quoteforge.admin maintenance email     # also email the digest
python -m quoteforge.admin maintenance --check    # report only, change nothing
```

**Safety boundaries — the agent never** edits code, spends money, flips paid
subscriptions, or deletes data. If the database integrity check ever fails, it
**stops and alerts** rather than attempting a risky auto-repair — that's your
cue to restore from a backup (`admin restore`).

## Reports on demand

The same engine produces reports at four cadences. View any on screen:
```powershell
python -m quoteforge.admin report daily
python -m quoteforge.admin report weekly
python -m quoteforge.admin report monthly
python -m quoteforge.admin report yearly
```
Add `email` to send instead of print: `... report monthly email`. (The
installer already schedules all four to email automatically.)

For exact monthly/yearly bookkeeping with a per-order Excel ledger, use
`python -m quoteforge.admin reconcile YYYY-MM` (see ETSY return/finance docs).

## What the daily report contains

- Total / In-Progress / Shipped / Error order counts
- Orders by status
- Pending customer messages + review requests
- Orders needing attention (stuck at proof or in error)
- **Tier / capacity alerts** — fires when monthly volume nears a plan limit
  (e.g. "Bannerbear: 850 is at 85% of Automate limit. Plan to upgrade to Scale.")
