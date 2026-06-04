# Daily Sales Report Email — Setup

A daily email to **ajacobusa@gmail.com** with order counts, follow-ups needed,
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
REPORT_RECIPIENT=ajacobusa@gmail.com
```

## Step 2 — Test it once

```powershell
python -m quoteforge.admin email-report
```
You should get the email within a minute. If it prints "not sent", the Gmail
credentials aren't set yet.

## Step 3 — Schedule it daily (Windows Task Scheduler)

1. Open **Task Scheduler** → Create Basic Task
2. Name: `QuoteForge Daily Report`
3. Trigger: **Daily**, time **7:30 AM**
4. Action: **Start a program**
   - Program/script: `python`
   - Arguments: `-m quoteforge.admin email-report`
   - Start in: `D:\ANOOP PERSONAL HOME\CLAUD\Claud AJ`
5. Finish. (Optional: check "Run whether user is logged on or not".)

PowerShell one-liner to create the task:
```powershell
$action  = New-ScheduledTaskAction -Execute "python" -Argument "-m quoteforge.admin email-report" -WorkingDirectory "D:\ANOOP PERSONAL HOME\CLAUD\Claud AJ"
$trigger = New-ScheduledTaskTrigger -Daily -At 7:30am
Register-ScheduledTask -TaskName "QuoteForge Daily Report" -Action $action -Trigger $trigger
```

## What the report contains

- Total / In-Progress / Shipped / Error order counts
- Orders by status
- Pending customer messages + review requests
- Orders needing attention (stuck at proof or in error)
- **Tier / capacity alerts** — fires when monthly volume nears a plan limit
  (e.g. "Bannerbear: 850 is at 85% of Automate limit. Plan to upgrade to Scale.")
