# Wireless Ops — 5-Minute Sales Demo Script

Live environment: **https://wireless-ops.vercel.app** (Vercel + Neon Postgres).

**Reset before every demo** (restores the pristine 8-property portfolio, then
re-runs a sync so timestamps read "just now"):

```bash
TOKEN=<ADMIN_TASK_TOKEN>
curl -X POST -H "Authorization: Bearer $TOKEN" https://wireless-ops.vercel.app/api/admin/db-setup
curl -X POST -H "Authorization: Bearer $TOKEN" https://wireless-ops.vercel.app/api/admin/sync
```

---

## The story

> "Coastline Hospitality runs 8 properties on 6 different WiFi vendors. One
> dashboard manages all of it — and one property is having a very bad week."

## 1. Dashboard (30s) — the portfolio at a glance

- 8 properties, average health, APs offline, critical alerts — one screen.
- Point at the **7d Δ column**: *"Harborview was at 91 a week ago. It's
  collapsing — and the platform caught it."* Worst sites sort to the top
  automatically.
- Note the vendor mix on /properties: **Aruba, Meraki, UniFi, RUCKUS,
  Fortinet, Mist** — same dashboard, vendor-agnostic.

## 2. Harborview property page (60s) — explainable health

- Click **Harborview Hotel & Spa**. The score isn't a black box: the
  **breakdown card itemizes every deduction** (critical alerts −24, offline
  AP −10, firmware lag −15…).
- The **sparkline** shows the week-long slide from 91.
- Click **"Explain this score"** — the AI writes the before/after narrative:
  *"Harborview dropped from 91 to 30 over the past week… fixing the critical
  alerts alone would lift the score to ~54."*

## 3. Alerts → Incidents (60s) — from noise to workflow

- **/alerts**: every alert ships with a **root cause and recommended action**
  (the playbook). Recurring issues escalate automatically — show the
  `recurring ×2` / `escalated from warning` chips.
- Click **"Create incident"** on an alert → lands in **/incidents** with a
  severity-based **SLA timer** (critical = 4h).
- On /incidents, expand the Harborview incident: **work-log notes**, owner
  assignment, and the automation note — *"Auto-escalated to vendor: SLA
  deadline passed"*. Nobody watched it; the platform escalated it.

## 4. IoT Security (45s) — the hotel-killer feature

- **/iot**: the headline finding — *"**Unknown IoT device detected on
  Harborview-Staff network** → Move to the IoT VLAN or quarantine via NAC."*
- Full segmentation inventory: VLAN, SSID, firewall zone, NAC policy, owner,
  approval status on every smart lock, camera, thermostat, kiosk.
- Newly discovered devices arrive **unapproved by default** and deduct from
  the property's health score until reviewed.

## 5. Vendors & Projects (45s) — operations, not just monitoring

- **/vendors**: circuit inventory with carrier refs ("what you read to the
  NOC"), the **degraded LTE backup** at Harborview, contracts flagged
  **"renews ≤90d"**, SLA terms and escalation paths per vendor.
- Expand **"Harborview guest WiFi remediation"**: milestones with progress,
  a **cutover checklist** and **post-deployment validation** — click a
  checkbox; it persists live.

## 6. AI assistant + audit (60s) — the close

- Back on the dashboard, click **"Weekly exec report"**: a leadership-ready
  paragraph in two seconds. Then **"What needs attention?"** — a ranked
  action list with first steps.
- **/audit**: every action just taken is in the **audit log** with
  before/after detail; the **role × permission matrix** (6 roles from Owner
  to read-only Executive) is enforced in code and rendered from the same
  source. Vendor credentials are AES-256-GCM encrypted.
- *"Everything you watched — sync, scoring, escalation, AI — runs on live
  Postgres. Aruba's live API connects with credentials and zero code
  changes; five more vendors are one adapter away."*

---

## Q&A crib notes

- **"Is this real data?"** Demo fixtures in a real production stack (Next.js
  on Vercel, Neon Postgres). Vendor adapters run in mock mode until API
  credentials are supplied; the entire pipeline (sync → normalize → score →
  auto-ticket) is the production code path.
- **"What does it cost to run?"** Free tiers cover the demo; ~$40/mo at
  small commercial scale (Vercel Pro + Neon Launch).
- **"How do new vendors get added?"** One adapter class + one registry line.
  The schema, scoring, alerting, and UI never change.
- **"Security?"** RBAC (6 roles), company isolation, property-level scoping,
  encrypted credentials, append-only audit log, login-activity capture.
