# Wireless Ops

A single dashboard to help hotels and small businesses manage WiFi, IoT, alerts,
vendors, and property health across a portfolio of sites.

This is the **first MVP slice**: dashboard shell + manual/normalized inventory +
Aruba Central integration + alerts + property health scoring. Other manufacturers
(Meraki, UniFi, Ruckus, Fortinet, Mist) and the AI layer are designed-for but not
yet built — see the roadmap below.

> **It runs with zero config.** No database, no auth keys, no Aruba credentials.
> The UI is served from a typed in-memory mock layer so you can `npm run dev` and
> see the whole product immediately. Real Postgres, Clerk, and the live Aruba API
> drop in behind the same interfaces with no UI changes.

## Stack

| Layer            | Choice                                             |
| ---------------- | -------------------------------------------------- |
| Framework        | Next.js 16 (App Router) + React 19 + TypeScript    |
| Styling          | Tailwind CSS v4                                     |
| Database         | Postgres (Vercel Marketplace / Neon) via Drizzle   |
| Auth             | Clerk (optional in dev)                            |
| Background jobs  | Inngest                                             |
| Hosting          | Vercel                                             |
| Heavy analytics  | Vercel Python on Fluid Compute (later)             |

## Quick start

```bash
npm install
npm run dev          # http://localhost:3000  → redirects to /dashboard
```

That's it. Everything below is optional and only needed to go from mock → live.

## Project structure

```
src/
  app/
    (app)/                 # authenticated shell (sidebar + topbar)
      dashboard/           # portfolio health overview
      properties/          # list + [id] detail (health breakdown, APs, IoT, alerts)
      devices/             # AP + IoT inventory across the portfolio
      alerts/              # alerts grouped by severity
      vendors/             # vendors + projects/deadlines
      integrations/        # vendor connection status + roadmap
    api/inngest/route.ts   # Inngest endpoint
  db/
    schema.ts              # Drizzle schema — SINGLE SOURCE OF TRUTH for types
    client.ts              # lazy Drizzle client (postgres.js)
    seed.ts                # seed DB from the same fixtures the UI uses
  lib/
    queries.ts             # the ONE data-access seam (mock today, DB later)
    health.ts              # 0-100 property health score + explainable breakdown
    mock/                  # typed fixtures (data.ts) + Aruba snapshots (aruba.ts)
  integrations/
    types.ts               # VendorAdapter interface (every manufacturer implements)
    aruba.ts               # Aruba Central adapter (mock + live stub)
    registry.ts            # vendor → adapter map (add a vendor = one line)
  inngest/                 # job client + vendor sync function
  components/              # sidebar, badges, cards, tables
  middleware.ts            # Clerk auth (enforced only when keys are present)
```

### Key design decisions

- **One data seam.** Every page calls `lib/queries.ts`. Today those functions
  return mock data; to go live you swap each body for a Drizzle query — no page,
  component, or scoring code changes. Types are inferred from `db/schema.ts`, so
  mock and DB can never drift.
- **One vendor interface.** `integrations/types.ts` defines `VendorAdapter`.
  Aruba Central implements it now; Meraki/UniFi/Ruckus/Fortinet/Mist each become
  a new adapter class plus one line in `registry.ts`.
- **Explainable health.** `health.ts` itemizes every deduction
  (`100 − critical alerts − offline APs − firmware lag − guest failures − IoT
  failures`), so the property page shows *why* a site scored what it did.

## Going live (optional, incremental)

**1. Database** — set `DATABASE_URL` (Vercel Marketplace Postgres or Neon) in
`.env.local`, then:

```bash
npm run db:migrate  # apply the committed SQL migrations in ./drizzle
npm run db:seed     # load the demo portfolio (safe to re-run; clears first)
npm run dev         # queries.ts auto-switches from mock to Postgres
npm run db:studio   # browse the data
```

No code changes needed — `queries.ts` is dual-mode and switches to Postgres
the moment `DATABASE_URL` exists (and back to mock when it doesn't). You can
prove the whole DB path locally without any server via:

```bash
npm run db:verify   # applies migrations + seeds + queries an embedded Postgres (PGlite)
```

**2. Auth** — add `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY`.
Auth turns on automatically; no code change needed.

**3. Background jobs** — `npm run inngest:dev` to run the job runner locally;
trigger a sync by sending the `vendor/sync.requested` event.

**4. Live Aruba Central** — provide credentials to `ArubaCentralAdapter`. The
exact REST endpoints to wire are marked inline in `src/integrations/aruba.ts`
(OAuth token refresh, `/monitoring/v2/aps`, `/monitoring/v1/clients`,
`/central/v1/alerts`). A webhook route for real-time alert ingest is the next add.

See `.env.example` for the full list of environment variables.

## Roadmap (from the build framework)

- [x] Step 1 — Dashboard shell (sidebar, company/property views)
- [x] Step 2 — Inventory (properties, APs, clients, IoT, vendors, projects)
- [x] Step 4 — Alerting (critical / warning / info) + alert intelligence:
      sync-time dedupe, root-cause tags + recommended actions (category
      playbook), recurrence detection with severity escalation, grouped views
      (property / category / vendor), and a raised/resolved history timeline
- [x] Step 5 — Health scoring (explainable 0-100 formula)
- [x] Step 6 — AI summaries via Vercel AI Gateway (Claude) with deterministic
      rule-based fallbacks: alert summary, "what needs attention today" action
      list, daily per-property brief, weekly executive report, vendor-blocker
      summary, and per-property "explain this health score"
- [x] Step 9 — Multi-vendor adapters (Aruba, Meraki, UniFi, RUCKUS, Fortinet, Mist)
- [x] Step 3 — Aruba Central sync pipeline: OAuth token flow, encrypted
      credential storage (`/api/admin/integrations`), normalized upserts into
      Postgres, sync-failure logging (`sync_runs` + `lastError`), last-synced
      timestamps, manual/cron trigger (`/api/admin/sync`) and Inngest job.
      *Live-API field mapping awaits real Aruba credentials for final tuning;
      webhook alert ingest still to come.*
- [x] Step 7 — IoT segmentation: VLAN / SSID / firewall zone / NAC policy /
      owner / approval lifecycle (approved · unapproved · quarantined) on every
      device, a dedicated IoT Security page with policy findings ("unknown
      device on staff network → move to IoT VLAN or quarantine"), and
      unapproved devices feeding the property health score
- [x] Ticketing & workflow automation — create incidents from alerts
      (one click on /alerts), owners, status flow (open · investigating ·
      vendor escalated · resolved), work-log notes, severity-based SLA timers
      (4h/24h/72h), and post-sync automation that auto-creates incidents for
      recurring alert groups and auto-escalates SLA breaches to the vendor
- [x] Step 8 — Vendor/project management: vendor contracts (start/end with
      ≤90-day renewal warnings), SLA terms, escalation paths, telecom circuit
      inventory (carrier ref, bandwidth, status, cost, contract end), project
      milestones with progress, and cutover + post-deployment validation
      checklists with one-click toggles
- [x] Security & RBAC — six roles (owner · admin · network engineer · property
      manager · vendor/MSP · read-only exec) with a code-enforced permission
      matrix, memberships for company isolation + property-level scoping,
      AES-256-GCM credential encryption, an append-only audit log with
      before/after change history, login-activity capture via Clerk webhook,
      and a Security & Audit page. Dev mode (no Clerk keys) acts as Owner so
      the demo stays public; adding Clerk keys enforces sign-in everywhere.
- [x] Sales-ready demo — before/after health story (score history snapshots,
      week-over-week Δ on the dashboard, sparklines on property pages,
      trend-aware AI reports: "dropped from 91 to 30 over the past week"),
      plus the full walkthrough script in [DEMO.md](DEMO.md) with one-command
      demo reset
- [ ] Step 10 — Automation (auto-ticket, auto-escalate, recommended fixes)
      *(partially done: ticketing automation auto-creates and auto-escalates)*
- [ ] Heavier analytics (RF tuning, anomaly detection) on Vercel Python / Fluid Compute
```
