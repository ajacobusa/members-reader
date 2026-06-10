import * as mock from "./mock/data";
import { computeHealth, type HealthResult } from "./health";
import type {
  AccessPoint,
  Alert,
  Client,
  Company,
  IotDevice,
  Incident,
  Integration,
  Project,
  Property,
  Vendor,
} from "@/db/schema";

/**
 * Data-access layer — the single seam between the UI and the data source.
 *
 * Today every function returns mock data (so the app runs with no database).
 * To go live, replace each body with a Drizzle query using getDb() from
 * @/db/client — the signatures and return types stay identical, so no page,
 * component, or scoring code changes.
 *
 * All functions are async on purpose: the DB-backed versions will be too.
 */

export async function getCompany(): Promise<Company> {
  return mock.companies[0];
}

export async function getProperties(): Promise<Property[]> {
  return mock.properties;
}

export async function getProperty(id: string): Promise<Property | undefined> {
  return mock.properties.find((p) => p.id === id);
}

export async function getIntegrations(): Promise<Integration[]> {
  return mock.integrations;
}

export async function getVendors(): Promise<Vendor[]> {
  return mock.vendors;
}

export async function getProjects(): Promise<Project[]> {
  return mock.projects;
}

export async function getIncidents(): Promise<Incident[]> {
  return mock.incidents;
}

export async function getAccessPoints(propertyId?: string): Promise<AccessPoint[]> {
  return filterByProperty(mock.accessPoints, propertyId);
}

export async function getClients(propertyId?: string): Promise<Client[]> {
  return filterByProperty(mock.clients, propertyId);
}

export async function getIotDevices(propertyId?: string): Promise<IotDevice[]> {
  return filterByProperty(mock.iotDevices, propertyId);
}

export async function getAlerts(propertyId?: string): Promise<Alert[]> {
  const rows = filterByProperty(mock.alerts, propertyId);
  return [...rows].sort((a, b) => b.raisedAt.getTime() - a.raisedAt.getTime());
}

function filterByProperty<T extends { propertyId: string | null }>(
  rows: T[],
  propertyId?: string
): T[] {
  return propertyId ? rows.filter((r) => r.propertyId === propertyId) : rows;
}

// ---------------------------------------------------------------------------
// Derived / aggregate views
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
  const [accessPoints, clients, iotDevices, alerts] = await Promise.all([
    getAccessPoints(property.id),
    getClients(property.id),
    getIotDevices(property.id),
    getAlerts(property.id),
  ]);
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
