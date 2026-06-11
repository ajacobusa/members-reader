// Shared reset-and-seed routine, used by BOTH the local CLI seed script
// (src/db/seed.ts) and the in-production admin endpoint (/api/admin/db-setup),
// so the two paths can never drift.
import type { PostgresJsDatabase } from "drizzle-orm/postgres-js";
import * as schema from "./schema";
import * as mock from "@/lib/mock/data";

// The Drizzle database handle shape produced by getDb().
type Db = PostgresJsDatabase<typeof schema>;

/**
 * Clear the demo data and reseed the full 8-property / 6-vendor portfolio.
 * Safe to re-run any time: deletes first (companies cascade to all children;
 * incidents cleared explicitly because their property link is nullable).
 * Returns row counts per table for verification/reporting.
 */
export async function resetAndSeed(db: Db): Promise<Record<string, number>> {
  // Reset. Most fixture rows get a fresh random UUID per process, so a re-run
  // must clear instead of relying on conflict handling.
  await db.delete(schema.incidents);
  await db.delete(schema.companies);

  // Insert in FK order (parents before children).
  await db.insert(schema.companies).values(mock.companies);
  await db.insert(schema.properties).values(mock.properties);
  await db.insert(schema.integrations).values(mock.integrations);
  await db.insert(schema.accessPoints).values(mock.accessPoints);
  await db.insert(schema.clients).values(mock.clients);
  await db.insert(schema.iotDevices).values(mock.iotDevices);
  await db.insert(schema.alerts).values(mock.alerts);
  await db.insert(schema.incidents).values(mock.incidents);
  await db.insert(schema.incidentNotes).values(mock.incidentNotes);
  await db.insert(schema.vendors).values(mock.vendors);
  await db.insert(schema.projects).values(mock.projects);
  await db.insert(schema.circuits).values(mock.circuits);
  await db.insert(schema.projectMilestones).values(mock.projectMilestones);
  await db.insert(schema.projectChecklist).values(mock.projectChecklist);
  await db.insert(schema.healthSnapshots).values(mock.healthSnapshots);

  // Report what landed so callers can verify at a glance.
  return {
    companies: mock.companies.length,
    properties: mock.properties.length,
    integrations: mock.integrations.length,
    accessPoints: mock.accessPoints.length,
    clients: mock.clients.length,
    iotDevices: mock.iotDevices.length,
    alerts: mock.alerts.length,
    incidents: mock.incidents.length,
    incidentNotes: mock.incidentNotes.length,
    vendors: mock.vendors.length,
    projects: mock.projects.length,
    circuits: mock.circuits.length,
    projectMilestones: mock.projectMilestones.length,
    projectChecklist: mock.projectChecklist.length,
    healthSnapshots: mock.healthSnapshots.length,
  };
}
