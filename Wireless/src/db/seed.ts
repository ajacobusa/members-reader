import "dotenv/config";
import { getDb } from "./client";
import * as schema from "./schema";
import * as mock from "@/lib/mock/data";

/**
 * Seed the database with the same fixtures the mock layer serves. Run with:
 *   npm run db:seed
 * Requires DATABASE_URL and a migrated schema (npm run db:push first).
 */
async function main() {
  const db = getDb();
  console.log("Seeding…");

  // Insert in FK order. onConflictDoNothing keeps the seed idempotent.
  await db.insert(schema.companies).values(mock.companies).onConflictDoNothing();
  await db.insert(schema.properties).values(mock.properties).onConflictDoNothing();
  await db.insert(schema.integrations).values(mock.integrations).onConflictDoNothing();
  await db.insert(schema.accessPoints).values(mock.accessPoints).onConflictDoNothing();
  await db.insert(schema.clients).values(mock.clients).onConflictDoNothing();
  await db.insert(schema.iotDevices).values(mock.iotDevices).onConflictDoNothing();
  await db.insert(schema.alerts).values(mock.alerts).onConflictDoNothing();
  await db.insert(schema.incidents).values(mock.incidents).onConflictDoNothing();
  await db.insert(schema.vendors).values(mock.vendors).onConflictDoNothing();
  await db.insert(schema.projects).values(mock.projects).onConflictDoNothing();

  console.log("Seed complete.");
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
