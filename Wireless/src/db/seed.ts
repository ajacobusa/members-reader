// Side-effect import: loads variables from `.env` into `process.env` so that
// DATABASE_URL is available when getDb() runs below.
import "dotenv/config";
// The factory that returns our shared Drizzle database client.
import { getDb } from "./client";
// The shared clear-then-insert routine (also used by /api/admin/db-setup).
import { resetAndSeed } from "./seed-data";

/**
 * Seed the database with the same fixtures the mock layer serves. Run with:
 *   npm run db:seed
 * Requires DATABASE_URL and a migrated schema (npm run db:migrate first).
 * Safe to re-run: it clears the demo data and reseeds from scratch.
 */
async function main() {
  // Get (and on first call, open) the database connection.
  const db = getDb();
  console.log("Seeding (clear + reinsert)…");
  // Run the shared routine and print the per-table row counts it reports.
  const counts = await resetAndSeed(db);
  console.table(counts);
  console.log("Seed complete.");
  // Exit 0 so the npm script reports success and the open connection
  // doesn't keep the process alive.
  process.exit(0);
}

// Kick off the async routine; any failure exits non-zero for CI/scripts.
main().catch((err) => {
  console.error(err);
  process.exit(1);
});
