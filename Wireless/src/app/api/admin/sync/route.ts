import { NextResponse } from "next/server";
import { desc } from "drizzle-orm";
import { adminAuthorized } from "@/lib/admin-auth";
import { syncAll } from "@/lib/sync";
import { getDb, hasDatabase, schema } from "@/db/client";
import { integrationVendor, type IntegrationVendorName } from "@/db/schema";

/**
 * Vendor sync trigger + audit log.
 *
 *   POST /api/admin/sync[?vendor=aruba_central]   run sync (all or one vendor)
 *   GET  /api/admin/sync                          last 20 sync runs
 *
 * Bearer-protected by ADMIN_TASK_TOKEN. Requires a database (sync writes
 * inventory rows); in mock mode it returns 400 with a clear message.
 */
export async function POST(req: Request) {
  if (!adminAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!hasDatabase()) {
    return NextResponse.json(
      { error: "sync requires DATABASE_URL (mock mode has nothing to write to)" },
      { status: 400 }
    );
  }

  // Optional vendor filter, validated against the enum.
  const raw = new URL(req.url).searchParams.get("vendor");
  let vendor: IntegrationVendorName | undefined;
  if (raw) {
    if (!(integrationVendor.enumValues as string[]).includes(raw)) {
      return NextResponse.json({ error: `unknown vendor "${raw}"` }, { status: 400 });
    }
    vendor = raw as IntegrationVendorName;
  }

  const { results, automation } = await syncAll(vendor);
  const ok = results.every((r) => r.ok);
  // Audit the machine-triggered sync (admin token identity).
  const { recordSystemAudit } = await import("@/lib/audit");
  await recordSystemAudit("admin-token", "sync.run", vendor ? `vendor:${vendor}` : "vendor:all", {
    ok,
    automation,
  });
  return NextResponse.json({ ok, results, automation }, { status: ok ? 200 : 502 });
}

export async function GET(req: Request) {
  if (!adminAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!hasDatabase()) {
    return NextResponse.json({ runs: [], note: "mock mode — no sync history" });
  }
  // Most recent runs first — the operator's sync audit trail.
  const runs = await getDb()
    .select()
    .from(schema.syncRuns)
    .orderBy(desc(schema.syncRuns.startedAt))
    .limit(20);
  return NextResponse.json({ runs });
}
