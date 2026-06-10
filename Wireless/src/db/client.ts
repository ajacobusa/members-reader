import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

/**
 * Drizzle client over postgres.js.
 *
 * Works with Vercel Marketplace Postgres / Neon (via the pooled connection
 * string) and with a local Postgres for development. The connection is created
 * lazily so the app boots without a DATABASE_URL — the UI runs on the mock data
 * layer until you point queries at the database.
 */

let _db: ReturnType<typeof drizzle<typeof schema>> | null = null;

export function getDb() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. The app runs on mock data by default; set " +
        "DATABASE_URL and switch lib/queries.ts to the DB-backed implementation."
    );
  }
  if (!_db) {
    // prepare: false is recommended for serverless / transaction-pooled connections.
    const client = postgres(url, { prepare: false });
    _db = drizzle(client, { schema });
  }
  return _db;
}

export function hasDatabase() {
  return Boolean(process.env.DATABASE_URL);
}

export { schema };
