// Drizzle helpers: `eq` builds a WHERE column = value clause, `desc` builds
// an ORDER BY ... DESC clause.
import { desc, eq } from "drizzle-orm";
// The lazy Drizzle client, the "is a database configured?" check, and the schema.
import { getDb, hasDatabase, schema } from "@/db/client";
// The in-memory fixtures used when no database is configured.
import * as mock from "./mock/data";
// The health-score calculator and its result type.
import { computeHealth, type HealthResult } from "./health";
// Row types inferred from the Drizzle schema — shared by both modes.
import type {
  AccessPoint,
  Alert,
  Client,
  Company,
  IotDevice,
  Incident,
  IncidentNote,
  Integration,
  Project,
  Property,
  Vendor,
  Circuit,
  ProjectMilestone,
  ProjectChecklistItem,
  HealthSnapshot,
} from "@/db/schema";

/**
 * Data-access layer — the single seam between the UI and the data source.
 *
 * DUAL MODE, chosen automatically per request:
 *  - DB mode: when DATABASE_URL is set, every function runs a real Drizzle
 *    query against Postgres (Neon / Vercel Marketplace / local).
 *  - Mock mode: with no DATABASE_URL, the same functions serve the typed
 *    in-memory fixtures, so the app still runs with zero config.
 *
 * Both modes return identical shapes (types are inferred from the schema), so
 * no page, component, or scoring code ever needs to know which mode is active.
 */

// ---------------------------------------------------------------------------
// Base reads — one function per table.
// ---------------------------------------------------------------------------

export async function getCompany(): Promise<Company> {
  if (hasDatabase()) {
    // Single-tenant for now: the first (only) company row.
    const rows = await getDb().select().from(schema.companies).limit(1);
    if (rows[0]) return rows[0];
    // An empty database (migrated but not seeded) falls through to the mock
    // company so the UI still renders something sensible.
  }
  return mock.companies[0];
}

export async function getProperties(): Promise<Property[]> {
  // Property-level permissions: scope the list to the current actor. With
  // Clerk off (dev mode) or a full-access membership this is a no-op; a
  // property-scoped user (e.g. one hotel's manager) only ever sees their
  // sites — and every derived view (portfolio, dashboards) inherits the scope.
  const { getActor, visibleProperties } = await import("./authz");
  const actor = await getActor();
  const all = hasDatabase()
    ? await getDb().select().from(schema.properties)
    : mock.properties;
  return visibleProperties(actor, all);
}

export async function getProperty(id: string): Promise<Property | undefined> {
  if (hasDatabase()) {
    const rows = await getDb()
      .select()
      .from(schema.properties)
      .where(eq(schema.properties.id, id))
      .limit(1);
    return rows[0];
  }
  return mock.properties.find((p) => p.id === id);
}

export async function getIntegrations(): Promise<Integration[]> {
  if (hasDatabase()) return getDb().select().from(schema.integrations);
  return mock.integrations;
}

export async function getVendors(): Promise<Vendor[]> {
  if (hasDatabase()) return getDb().select().from(schema.vendors);
  return mock.vendors;
}

export async function getProjects(): Promise<Project[]> {
  if (hasDatabase()) return getDb().select().from(schema.projects);
  return mock.projects;
}

export async function getCircuits(): Promise<Circuit[]> {
  if (hasDatabase()) return getDb().select().from(schema.circuits);
  return mock.circuits;
}

export async function getHealthSnapshots(): Promise<HealthSnapshot[]> {
  if (hasDatabase()) {
    // Chronological — pages group by property and feed sparklines/trends.
    return getDb().select().from(schema.healthSnapshots).orderBy(schema.healthSnapshots.at);
  }
  return mock.healthSnapshots;
}

export async function getProjectMilestones(): Promise<ProjectMilestone[]> {
  if (hasDatabase()) {
    // Ordered for display: project grouping happens in the page.
    return getDb().select().from(schema.projectMilestones).orderBy(schema.projectMilestones.sortOrder);
  }
  return mock.projectMilestones;
}

export async function getProjectChecklist(): Promise<ProjectChecklistItem[]> {
  if (hasDatabase()) {
    return getDb().select().from(schema.projectChecklist).orderBy(schema.projectChecklist.sortOrder);
  }
  return mock.projectChecklist;
}

export async function getIncidents(): Promise<Incident[]> {
  if (hasDatabase()) return getDb().select().from(schema.incidents);
  return mock.incidents;
}

export async function getIncidentNotes(): Promise<IncidentNote[]> {
  if (hasDatabase()) {
    // Oldest first — notes read as a chronological work log.
    return getDb().select().from(schema.incidentNotes).orderBy(schema.incidentNotes.createdAt);
  }
  return mock.incidentNotes;
}

export async function getAccessPoints(propertyId?: string): Promise<AccessPoint[]> {
  if (hasDatabase()) {
    const q = getDb().select().from(schema.accessPoints);
    // With a property id, narrow to that site; otherwise return the whole fleet.
    return propertyId ? q.where(eq(schema.accessPoints.propertyId, propertyId)) : q;
  }
  return filterByProperty(mock.accessPoints, propertyId);
}

export async function getClients(propertyId?: string): Promise<Client[]> {
  if (hasDatabase()) {
    const q = getDb().select().from(schema.clients);
    return propertyId ? q.where(eq(schema.clients.propertyId, propertyId)) : q;
  }
  return filterByProperty(mock.clients, propertyId);
}

export async function getIotDevices(propertyId?: string): Promise<IotDevice[]> {
  if (hasDatabase()) {
    const q = getDb().select().from(schema.iotDevices);
    return propertyId ? q.where(eq(schema.iotDevices.propertyId, propertyId)) : q;
  }
  return filterByProperty(mock.iotDevices, propertyId);
}

export async function getAlerts(propertyId?: string): Promise<Alert[]> {
  if (hasDatabase()) {
    // Newest first, pushed down to Postgres as ORDER BY raised_at DESC.
    const q = getDb()
      .select()
      .from(schema.alerts)
      .orderBy(desc(schema.alerts.raisedAt));
    return propertyId ? q.where(eq(schema.alerts.propertyId, propertyId)) : q;
  }
  const rows = filterByProperty(mock.alerts, propertyId);
  // Mock mode sorts in memory to match the DB ordering exactly.
  return [...rows].sort((a, b) => b.raisedAt.getTime() - a.raisedAt.getTime());
}

// Mock-mode helper: keep rows belonging to one property, or all rows if no id.
function filterByProperty<T extends { propertyId: string | null }>(
  rows: T[],
  propertyId?: string
): T[] {
  return propertyId ? rows.filter((r) => r.propertyId === propertyId) : rows;
}

// ---------------------------------------------------------------------------
// Derived / aggregate views — built on the base reads, so they work
// identically in both modes with no extra branching.
// ---------------------------------------------------------------------------

export interface PropertyOverview {
  property: Property;
  health: HealthResult;
  apCount: number;
  apOffline: number;
  clientCount: number;
  iotCount: number;
  openAlerts: number;
  criticalAlerts: number;
}

export async function getPropertyOverview(
  property: Property
): Promise<PropertyOverview> {
  // Fetch the four per-site datasets in parallel.
  const [accessPoints, clients, iotDevices, alerts] = await Promise.all([
    getAccessPoints(property.id),
    getClients(property.id),
    getIotDevices(property.id),
    getAlerts(property.id),
  ]);
  // Health is always computed live from the rows (never read from the cached column).
  const health = computeHealth({ accessPoints, clients, iotDevices, alerts });
  const openAlerts = alerts.filter((a) => a.status !== "resolved");
  return {
    property,
    health,
    apCount: accessPoints.length,
    apOffline: accessPoints.filter((ap) => ap.status === "offline").length,
    clientCount: clients.length,
    iotCount: iotDevices.length,
    openAlerts: openAlerts.length,
    criticalAlerts: openAlerts.filter((a) => a.severity === "critical").length,
  };
}

export async function getPortfolio(): Promise<PropertyOverview[]> {
  const properties = await getProperties();
  // Note: in DB mode this is N+1 queries (4 per property). Fine at this scale;
  // optimize with grouped aggregate queries when the portfolio grows.
  const overviews = await Promise.all(properties.map(getPropertyOverview));
  return overviews.sort((a, b) => a.health.score - b.health.score); // worst first
}

export interface AlertCounts {
  critical: number;
  warning: number;
  info: number;
  total: number;
}

export async function getAlertCounts(propertyId?: string): Promise<AlertCounts> {
  const alerts = (await getAlerts(propertyId)).filter((a) => a.status !== "resolved");
  return {
    critical: alerts.filter((a) => a.severity === "critical").length,
    warning: alerts.filter((a) => a.severity === "warning").length,
    info: alerts.filter((a) => a.severity === "info").length,
    total: alerts.length,
  };
}

/** Recurring-issue rollup by alert category (feeds the "recurring issues" view). */
export async function getRecurringIssues(): Promise<
  { category: string; count: number }[]
> {
  const alerts = await getAlerts();
  const counts = new Map<string, number>();
  for (const a of alerts) {
    const key = a.category ?? "uncategorized";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count);
}
