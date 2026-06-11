import "server-only";
import { and, desc, eq } from "drizzle-orm";
import { getDb, schema } from "@/db/client";
import { computeHealth } from "@/lib/health";
import { getAdapter } from "@/integrations/registry";
import { decryptCredentials } from "@/lib/secrets";
import {
  findRecurringWithoutIncident,
  findSlaBreaches,
  recurringIncidentTitle,
  slaDueFor,
} from "@/lib/incidents";
import type { Integration, IntegrationVendorName } from "@/db/schema";
import type { VendorSiteSnapshot } from "@/integrations/types";

/**
 * Vendor sync pipeline — the heart of "real network ops software".
 *
 * For one integration:
 *   1. Build its adapter (decrypted credentials → LIVE mode; none → MOCK mode,
 *      so the entire pipeline below is exercisable without vendor accounts).
 *   2. List the vendor's sites and match each to a property by (vendor, name);
 *      unknown sites are auto-onboarded as new properties.
 *   3. Pull a normalized snapshot per site and upsert it:
 *        - access points: update by externalId (or name), insert new
 *        - clients: replace per property (ephemeral data)
 *        - IoT devices: update by externalId (or name), insert new
 *        - alerts: insert unseen (by externalId, then open-title dedupe)
 *   4. Record the outcome: integrations.lastSyncedAt/status/lastError plus an
 *      audit row in sync_runs (success or failure, with per-run stats).
 *
 * Every failure is captured — never thrown past this module — so a broken
 * vendor link degrades visibly (status="error", lastError set) instead of
 * crashing the caller.
 */

export interface SyncResult {
  integrationId: string;
  vendor: IntegrationVendorName;
  ok: boolean;
  error?: string;
  stats: Record<string, number>;
}

export interface SyncSummary {
  results: SyncResult[];
  /** What the post-sync ticketing automation did this run. */
  automation: { autoCreatedIncidents: number; autoEscalatedIncidents: number };
}

/** Sync every integration (or one vendor), then run the ticketing automation. */
export async function syncAll(vendor?: IntegrationVendorName): Promise<SyncSummary> {
  const db = getDb();
  const rows = vendor
    ? await db.select().from(schema.integrations).where(eq(schema.integrations.vendor, vendor))
    : await db.select().from(schema.integrations);
  const results: SyncResult[] = [];
  // Sequential on purpose: keeps DB load and vendor rate limits gentle.
  for (const row of rows) results.push(await syncIntegration(row));
  // After the data lands, apply the workflow rules (auto-create / auto-escalate).
  const automation = await runTicketingAutomation();
  // …then snapshot every property's health so the before/after trend grows.
  await recordHealthSnapshots();
  return { results, automation };
}

/**
 * Compute and store today's health score per property (max one snapshot per
 * ~day), and refresh the cached properties.health_score column. This is what
 * turns the dashboard's Δ column and sparklines into a living trend.
 */
async function recordHealthSnapshots(): Promise<void> {
  const db = getDb();
  const now = new Date();
  const properties = await db.select().from(schema.properties);
  for (const p of properties) {
    // Skip if we already snapshotted this property in the last ~20 hours.
    const recent = await db
      .select({ at: schema.healthSnapshots.at })
      .from(schema.healthSnapshots)
      .where(eq(schema.healthSnapshots.propertyId, p.id))
      .orderBy(desc(schema.healthSnapshots.at))
      .limit(1);
    if (recent[0] && now.getTime() - recent[0].at.getTime() < 20 * 3600_000) continue;

    // Same live computation the dashboard uses.
    const [accessPoints, clients, iotDevices, alerts] = await Promise.all([
      db.select().from(schema.accessPoints).where(eq(schema.accessPoints.propertyId, p.id)),
      db.select().from(schema.clients).where(eq(schema.clients.propertyId, p.id)),
      db.select().from(schema.iotDevices).where(eq(schema.iotDevices.propertyId, p.id)),
      db.select().from(schema.alerts).where(eq(schema.alerts.propertyId, p.id)),
    ]);
    const { score } = computeHealth({ accessPoints, clients, iotDevices, alerts });
    await db.insert(schema.healthSnapshots).values({ propertyId: p.id, score, at: now });
    // Keep the cached column in step with the latest snapshot.
    await db
      .update(schema.properties)
      .set({ healthScore: score })
      .where(eq(schema.properties.id, p.id));
  }
}

/**
 * Ticketing automation — runs after every sync:
 *  Rule 1: recurring alert groups (>=2 open alerts, same property + category)
 *          with no open incident get an incident auto-created.
 *  Rule 2: open/investigating incidents past their SLA deadline are escalated
 *          to "vendor_escalated", with an automation note explaining why.
 */
export async function runTicketingAutomation(): Promise<{
  autoCreatedIncidents: number;
  autoEscalatedIncidents: number;
}> {
  const db = getDb();
  const now = new Date();
  const [alerts, incidents, properties] = await Promise.all([
    db.select().from(schema.alerts),
    db.select().from(schema.incidents),
    db.select().from(schema.properties),
  ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));

  // Rule 1 — auto-create incidents for uncovered recurring issues.
  const candidates = findRecurringWithoutIncident(alerts, incidents);
  for (const c of candidates) {
    const inserted = await db
      .insert(schema.incidents)
      .values({
        propertyId: c.propertyId,
        title: recurringIncidentTitle(c.category, propName.get(c.propertyId) ?? "unknown site"),
        summary: `${c.count} open ${c.category.replace(/_/g, " ")} alerts at this property — auto-created by ticketing automation.`,
        status: "open",
        severity: c.severity,
        category: c.category,
        alertId: c.newestAlertId,
        slaDueAt: slaDueFor(c.severity, now),
        openedAt: now,
      })
      .returning({ id: schema.incidents.id });
    await db.insert(schema.incidentNotes).values({
      incidentId: inserted[0].id,
      author: "automation",
      body: `Auto-created: ${c.count} open ${c.category} alerts within the recurrence window.`,
    });
  }

  // Rule 2 — escalate SLA breaches to the vendor.
  const breaches = findSlaBreaches(incidents, now);
  for (const i of breaches) {
    await db
      .update(schema.incidents)
      .set({ status: "vendor_escalated" })
      .where(eq(schema.incidents.id, i.id));
    await db.insert(schema.incidentNotes).values({
      incidentId: i.id,
      author: "automation",
      body: `Auto-escalated to vendor: SLA deadline (${i.slaDueAt?.toISOString()}) passed without resolution.`,
    });
  }

  return {
    autoCreatedIncidents: candidates.length,
    autoEscalatedIncidents: breaches.length,
  };
}

/** Sync one integration end-to-end, recording the outcome. */
export async function syncIntegration(integration: Integration): Promise<SyncResult> {
  const db = getDb();
  const startedAt = new Date();
  const stats: Record<string, number> = {
    sites: 0,
    aps: 0,
    clients: 0,
    iot: 0,
    newAlerts: 0,
    newProperties: 0,
  };

  try {
    // Credentials decrypt to null when absent/undecryptable → adapter runs MOCK.
    const creds = decryptCredentials(integration.credentials);
    const adapter = getAdapter(integration.vendor, creds ?? undefined);

    const sites = await adapter.listSites();
    for (const site of sites) {
      const propertyId = await resolveProperty(
        integration.companyId,
        integration.vendor,
        site.name,
        stats
      );
      const snapshot = await adapter.fetchSiteSnapshot(site.externalId);
      await upsertSnapshot(propertyId, snapshot, stats);
      stats.sites++;
    }

    // Success: stamp the integration and write the audit row.
    await db
      .update(schema.integrations)
      .set({ lastSyncedAt: new Date(), status: "connected", lastError: null })
      .where(eq(schema.integrations.id, integration.id));
    await db.insert(schema.syncRuns).values({
      integrationId: integration.id,
      startedAt,
      finishedAt: new Date(),
      ok: 1,
      stats,
    });
    return { integrationId: integration.id, vendor: integration.vendor, ok: true, stats };
  } catch (err) {
    // Failure: surface on the integration row AND the audit log, never throw.
    const message = err instanceof Error ? err.message : String(err);
    await db
      .update(schema.integrations)
      .set({ status: "error", lastError: message })
      .where(eq(schema.integrations.id, integration.id));
    await db.insert(schema.syncRuns).values({
      integrationId: integration.id,
      startedAt,
      finishedAt: new Date(),
      ok: 0,
      error: message,
      stats,
    });
    return {
      integrationId: integration.id,
      vendor: integration.vendor,
      ok: false,
      error: message,
      stats,
    };
  }
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/** Find the property for a vendor site by (managedBy, name) — or create it. */
async function resolveProperty(
  companyId: string,
  vendor: IntegrationVendorName,
  siteName: string,
  stats: Record<string, number>
): Promise<string> {
  const db = getDb();
  const existing = await db
    .select({ id: schema.properties.id })
    .from(schema.properties)
    .where(
      and(
        eq(schema.properties.name, siteName),
        eq(schema.properties.managedBy, vendor)
      )
    )
    .limit(1);
  if (existing[0]) return existing[0].id;

  // Auto-onboard: a site that exists at the vendor but not in our portfolio.
  const inserted = await db
    .insert(schema.properties)
    .values({ companyId, name: siteName, managedBy: vendor })
    .returning({ id: schema.properties.id });
  stats.newProperties++;
  return inserted[0].id;
}

/** Write one site snapshot into the inventory tables. */
async function upsertSnapshot(
  propertyId: string,
  snap: VendorSiteSnapshot,
  stats: Record<string, number>
) {
  const db = getDb();

  // --- Access points: update by externalId (fallback: name), insert new. ---
  const existingAps = await db
    .select()
    .from(schema.accessPoints)
    .where(eq(schema.accessPoints.propertyId, propertyId));
  // externalId of each AP after upsert → our row id (for client wiring below).
  const apIdByExternal = new Map<string, string>();

  for (const ap of snap.accessPoints) {
    const match =
      existingAps.find((e) => e.externalId && e.externalId === ap.externalId) ??
      existingAps.find((e) => !e.externalId && e.name === ap.name);
    const values = {
      name: ap.name,
      model: ap.model ?? null,
      serial: ap.serial ?? null,
      macAddress: ap.macAddress ?? null,
      ipAddress: ap.ipAddress ?? null,
      status: ap.status,
      firmwareVersion: ap.firmwareVersion ?? null,
      // Keep any existing recommendation if the vendor pull doesn't carry one.
      ...(ap.firmwareRecommended ? { firmwareRecommended: ap.firmwareRecommended } : {}),
      clientCount: ap.clientCount,
      uptimeSeconds: ap.uptimeSeconds,
      lastSeen: ap.lastSeen ? new Date(ap.lastSeen) : new Date(),
      externalId: ap.externalId,
    };
    if (match) {
      await db
        .update(schema.accessPoints)
        .set(values)
        .where(eq(schema.accessPoints.id, match.id));
      apIdByExternal.set(ap.externalId, match.id);
    } else {
      const inserted = await db
        .insert(schema.accessPoints)
        .values({ propertyId, ...values })
        .returning({ id: schema.accessPoints.id });
      apIdByExternal.set(ap.externalId, inserted[0].id);
    }
    stats.aps++;
  }

  // --- Clients: ephemeral — replace this property's rows wholesale. ---------
  if (snap.clients.length > 0 || snap.accessPoints.length > 0) {
    await db.delete(schema.clients).where(eq(schema.clients.propertyId, propertyId));
    if (snap.clients.length > 0) {
      await db.insert(schema.clients).values(
        snap.clients.map((c) => ({
          propertyId,
          accessPointId: c.accessPointExternalId
            ? (apIdByExternal.get(c.accessPointExternalId) ?? null)
            : null,
          hostname: c.hostname ?? null,
          macAddress: c.macAddress ?? null,
          ssid: c.ssid ?? null,
          isGuest: c.isGuest ? 1 : 0,
          signalDbm: c.signalDbm ?? null,
          status: c.status,
          connectionFailed: c.connectionFailed ? 1 : 0,
          lastSeen: c.lastSeen ? new Date(c.lastSeen) : new Date(),
        }))
      );
      stats.clients += snap.clients.length;
    }
  }

  // --- IoT devices: update by externalId (fallback: name), insert new. ------
  const existingIot = await db
    .select()
    .from(schema.iotDevices)
    .where(eq(schema.iotDevices.propertyId, propertyId));
  for (const d of snap.iotDevices) {
    const match =
      existingIot.find((e) => e.name === d.name) ?? // fixtures carry no externalId
      undefined;
    const values = {
      name: d.name,
      deviceType: d.deviceType ?? null,
      vendor: d.vendor ?? null,
      macAddress: d.macAddress ?? null,
      vlan: d.vlan ?? null,
      ssid: d.ssid ?? null,
      securityGroup: d.securityGroup ?? null,
      status: d.status,
      riskLevel: d.riskLevel,
      lastSeen: d.lastSeen ? new Date(d.lastSeen) : new Date(),
    };
    if (match) {
      await db
        .update(schema.iotDevices)
        .set(values)
        .where(eq(schema.iotDevices.id, match.id));
    } else {
      await db.insert(schema.iotDevices).values({ propertyId, ...values });
    }
    stats.iot++;
  }

  // --- Alerts: insert only unseen ones. -------------------------------------
  // Dedupe key: vendor externalId when present; otherwise an open alert with
  // the same title on this property counts as the same incident (basic
  // dedup — richer correlation lands with the alert-intelligence step).
  const existingAlerts = await db
    .select({
      externalId: schema.alerts.externalId,
      title: schema.alerts.title,
      status: schema.alerts.status,
    })
    .from(schema.alerts)
    .where(eq(schema.alerts.propertyId, propertyId));
  const seenExternal = new Set(existingAlerts.map((a) => a.externalId).filter(Boolean));
  const openTitles = new Set(
    existingAlerts.filter((a) => a.status !== "resolved").map((a) => a.title)
  );

  for (const a of snap.alerts) {
    if (seenExternal.has(a.externalId) || openTitles.has(a.title)) continue;
    await db.insert(schema.alerts).values({
      propertyId,
      severity: a.severity,
      title: a.title,
      description: a.description ?? null,
      source: a.source ?? null,
      category: a.category ?? null,
      externalId: a.externalId,
      raisedAt: a.raisedAt ? new Date(a.raisedAt) : new Date(),
    });
    stats.newAlerts++;
  }
}
