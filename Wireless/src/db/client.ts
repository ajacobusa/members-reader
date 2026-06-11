// `drizzle` wraps a raw database connection in the Drizzle ORM query builder.
// We import the postgres-js flavor because our driver below is the `postgres`
// package (a.k.a. postgres.js).
import { drizzle } from "drizzle-orm/postgres-js";
// `postgres` is the low-level Postgres driver (postgres.js). It opens the actual
// TCP connection and sends SQL to the database.
import postgres from "postgres";
// Import every export from schema.ts under the name `schema`. Passing this to
// Drizzle teaches the ORM about our tables so queries are fully typed.
import * as schema from "./schema";

/**
 * Drizzle client over postgres.js.
 *
 * Works with Vercel Marketplace Postgres / Neon (via the pooled connection
 * string) and with a local Postgres for development. The connection is created
 * lazily so the app boots without a DATABASE_URL — the UI runs on the mock data
 * layer until you point queries at the database.
 */

// Module-level cache for the single Drizzle instance (the "singleton" pattern).
// `ReturnType<typeof drizzle<typeof schema>>` is the exact type that `drizzle()`
// returns for our schema. It starts as `null` and is filled in on first use, so
// we only ever open one database connection per process.
let _db: ReturnType<typeof drizzle<typeof schema>> | null = null;

// Returns the shared Drizzle database client, creating it the first time it's
// called. Side effect: opens a real Postgres connection on first call.
// Throws if DATABASE_URL is not configured.
export function getDb() {
  // Read the connection string from the environment.
  const url = process.env.DATABASE_URL;
  // If there is no URL, fail loudly with a helpful message instead of crashing
  // later with a cryptic connection error.
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. The app runs on mock data by default; set " +
        "DATABASE_URL and switch lib/queries.ts to the DB-backed implementation."
    );
  }
  // Only build the client once. On later calls `_db` is already set, so we skip
  // straight to returning it (lazy initialization).
  if (!_db) {
    // prepare: false is recommended for serverless / transaction-pooled connections.
    // (Prepared statements don't survive across pooled connections, so we disable them.)
    const client = postgres(url, { prepare: false });
    // Wrap the raw driver with Drizzle, passing the schema so queries are typed.
    _db = drizzle(client, { schema });
  }
  // Hand back the cached (now guaranteed non-null) Drizzle client.
  return _db;
}

// Quick boolean check used by callers to decide whether to use real DB queries
// or fall back to the mock data layer. Returns true only when DATABASE_URL exists.
export function hasDatabase() {
  // `Boolean(...)` converts the string-or-undefined value into a plain true/false.
  return Boolean(process.env.DATABASE_URL);
}

// Re-export the schema so other modules can import tables/types from this single
// client entry point instead of reaching into schema.ts directly.
export { schema };
