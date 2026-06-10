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
npm run db:push     # create tables from the schema
npm run db:seed     # load the demo fixtures
npm run db:studio   # browse the data
```

Then switch the bodies in `src/lib/queries.ts` from `mock.*` to Drizzle queries.

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
- [x] Step 4 — Alerting (critical / warning / info)
- [x] Step 5 — Health scoring (explainable 0-100 formula)
- [ ] Step 3 — Connect **live** Aruba Central (adapter + webhook)
- [ ] Step 6 — AI summaries (Vercel AI Gateway; Python on Fluid Compute)
- [ ] Step 7 — IoT segmentation tracking (NAC/firewall zone enrichment)
- [ ] Step 8 — Vendor/project workflows (milestones, blockers, SLA)
- [ ] Step 9 — More manufacturers (Meraki, UniFi, Ruckus, Fortinet, Mist)
- [ ] Step 10 — Automation (auto-ticket, auto-escalate, recommended fixes)
```
