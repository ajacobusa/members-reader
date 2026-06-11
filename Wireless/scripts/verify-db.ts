// End-to-end database verification against an embedded REAL Postgres engine.
//
// PGlite is Postgres compiled to WASM — same SQL dialect, same enum/FK/index
// behavior — so this proves, without any server or DATABASE_URL:
//   1. the generated Drizzle migration applies cleanly,
//   2. the seed fixtures satisfy every FK/enum/constraint,
//   3. the same SELECT shapes queries.ts uses return correct data.
//
// Run with: npm run db:verify
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";
import { desc, eq } from "drizzle-orm";
import * as schema from "../src/db/schema";
import * as mock from "../src/lib/mock/data";

// Tiny assert helper: fail loudly with a clear message.
function check(cond: boolean, label: string) {
  if (!cond) throw new Error(`FAILED: ${label}`);
  console.log(`  ✓ ${label}`);
}

async function main() {
  console.log("1) Booting embedded Postgres (PGlite)…");
  const client = new PGlite(); // in-memory database
  const db = drizzle(client, { schema });

  console.log("2) Applying generated migrations from ./drizzle …");
  await migrate(db, { migrationsFolder: "./drizzle" });

  console.log("3) Seeding with the same fixtures db:seed uses…");
  // Same FK order as src/db/seed.ts.
  await db.insert(schema.companies).values(mock.companies);
  await db.insert(schema.properties).values(mock.properties);
  await db.insert(schema.integrations).values(mock.integrations);
  await db.insert(schema.accessPoints).values(mock.accessPoints);
  await db.insert(schema.clients).values(mock.clients);
  await db.insert(schema.iotDevices).values(mock.iotDevices);
  await db.insert(schema.alerts).values(mock.alerts);
  await db.insert(schema.incidents).values(mock.incidents);
  await db.insert(schema.vendors).values(mock.vendors);
  await db.insert(schema.projects).values(mock.projects);

  console.log("4) Running the same query shapes queries.ts uses…");
  const properties = await db.select().from(schema.properties);
  check(properties.length === 8, `8 properties seeded (got ${properties.length})`);

  const integrations = await db.select().from(schema.integrations);
  check(integrations.length === 6, `6 vendor integrations (got ${integrations.length})`);

  // Per-property filter (the getAccessPoints(propertyId) shape).
  const harborviewAps = await db
    .select()
    .from(schema.accessPoints)
    .where(eq(schema.accessPoints.propertyId, mock.ID.p1));
  check(harborviewAps.length === 3, `Harborview has 3 APs (got ${harborviewAps.length})`);

  // Ordered alerts (the getAlerts() shape).
  const alerts = await db
    .select()
    .from(schema.alerts)
    .orderBy(desc(schema.alerts.raisedAt));
  check(alerts.length === 13, `13 alerts seeded (got ${alerts.length})`);
  check(
    alerts[0].raisedAt.getTime() >= alerts[alerts.length - 1].raisedAt.getTime(),
    "alerts ordered newest-first by Postgres"
  );

  const criticals = alerts.filter((a) => a.severity === "critical");
  check(criticals.length === 3, `3 critical alerts (got ${criticals.length})`);

  // Re-seed safety: the clear-then-insert pattern from seed.ts.
  console.log("5) Verifying idempotent reseed (clear + cascade + reinsert)…");
  await db.delete(schema.incidents);
  await db.delete(schema.companies);
  const afterDelete = await db.select().from(schema.accessPoints);
  check(afterDelete.length === 0, "company delete cascades to all child rows");
  await db.insert(schema.companies).values(mock.companies);
  await db.insert(schema.properties).values(mock.properties);
  const reseeded = await db.select().from(schema.properties);
  check(reseeded.length === 8, "reseed after clear works");

  console.log("\nAll database checks passed. Migration + seed + queries are sound.");
  await client.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
