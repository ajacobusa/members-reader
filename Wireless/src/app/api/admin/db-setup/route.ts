import { NextResponse } from "next/server";
import { adminAuthorized } from "@/lib/admin-auth";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";
import { sql } from "drizzle-orm";
import * as schema from "@/db/schema";
import { resetAndSeed } from "@/db/seed-data";

/**
 * One-shot database setup endpoint — runs INSIDE the deployment, where the
 * (sensitive, write-only) DATABASE_URL already exists. This lets us migrate
 * and seed a Marketplace database without ever exporting its secret.
 *
 *   POST /api/admin/db-setup   Authorization: Bearer <ADMIN_TASK_TOKEN>
 *     → applies ./drizzle migrations, then clears + reseeds the demo data.
 *   GET  /api/admin/db-setup   Authorization: Bearer <ADMIN_TASK_TOKEN>
 *     → reports whether a DB is configured and current table counts.
 *
 * Protected by ADMIN_TASK_TOKEN (a long random secret in the project env).
 * Without that env var the endpoint refuses everything, so it is inert unless
 * explicitly armed.
 */

// Prefer the direct (unpooled) connection for DDL; fall back to the pooled URL.
function connectionUrl(): string | undefined {
  return process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL;
}

export async function POST(req: Request) {
  if (!adminAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const url = connectionUrl();
  if (!url) {
    return NextResponse.json({ error: "no DATABASE_URL configured" }, { status: 400 });
  }
  // ?seed=0 applies migrations only (no data reset) — for schema upgrades on a
  // database whose contents should be preserved.
  const wantSeed = new URL(req.url).searchParams.get("seed") !== "0";

  // A dedicated single connection, closed when done (serverless-friendly).
  const client = postgres(url, { max: 1, prepare: false });
  const db = drizzle(client, { schema });
  try {
    // 1) Apply the committed SQL migrations (bundled via outputFileTracingIncludes).
    await migrate(db, { migrationsFolder: "./drizzle" });
    // 2) Optionally clear + reseed the demo portfolio with the shared routine.
    const seeded = wantSeed ? await resetAndSeed(db) : null;
    // Audit the maintenance operation (admin token identity).
    const { recordSystemAudit } = await import("@/lib/audit");
    await recordSystemAudit("admin-token", "admin.db-setup", undefined, {
      migrated: true,
      reseeded: wantSeed,
    });
    return NextResponse.json({ ok: true, migrated: true, seeded });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 }
    );
  } finally {
    await client.end();
  }
}

export async function GET(req: Request) {
  if (!adminAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const url = connectionUrl();
  if (!url) {
    return NextResponse.json({ db: false, reason: "no DATABASE_URL configured" });
  }

  const client = postgres(url, { max: 1, prepare: false });
  const db = drizzle(client, { schema });
  try {
    // Lightweight liveness + row counts straight from Postgres.
    const [props, aps, alerts] = await Promise.all([
      db.execute(sql`select count(*)::int as n from properties`),
      db.execute(sql`select count(*)::int as n from access_points`),
      db.execute(sql`select count(*)::int as n from alerts`),
    ]);
    return NextResponse.json({
      db: true,
      counts: {
        properties: Number(props[0]?.n ?? 0),
        accessPoints: Number(aps[0]?.n ?? 0),
        alerts: Number(alerts[0]?.n ?? 0),
      },
    });
  } catch (err) {
    // Tables missing (migrations not applied yet) or connection failure.
    return NextResponse.json({
      db: true,
      ready: false,
      error: err instanceof Error ? err.message : String(err),
    });
  } finally {
    await client.end();
  }
}
