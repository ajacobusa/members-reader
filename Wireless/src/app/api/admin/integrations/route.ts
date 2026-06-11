import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { z } from "zod";
import { adminAuthorized } from "@/lib/admin-auth";
import { encryptCredentials, encryptionAvailable } from "@/lib/secrets";
import { getDb, hasDatabase, schema } from "@/db/client";
import { integrationVendor } from "@/db/schema";

/**
 * Set vendor API credentials — encrypted at rest.
 *
 *   POST /api/admin/integrations
 *   { "vendor": "aruba_central",
 *     "baseUrl": "https://apigw-uswest4.central.arubanetworks.com",
 *     "credentials": { "clientId": "...", "clientSecret": "...",
 *                      "refreshToken": "...", "customerId": "..." } }
 *
 * The credentials object is AES-256-GCM encrypted with
 * CREDENTIALS_ENCRYPTION_KEY before it touches Postgres; without that env var
 * the request is refused (secrets are never stored plaintext). Bearer-protected
 * by ADMIN_TASK_TOKEN. The next sync for this vendor then runs in LIVE mode.
 */

const Body = z.object({
  vendor: z.enum(integrationVendor.enumValues),
  baseUrl: z.string().url().optional(),
  label: z.string().min(1).optional(),
  credentials: z.record(z.string(), z.string()),
});

export async function POST(req: Request) {
  if (!adminAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!hasDatabase()) {
    return NextResponse.json({ error: "requires DATABASE_URL" }, { status: 400 });
  }
  if (!encryptionAvailable()) {
    return NextResponse.json(
      { error: "CREDENTIALS_ENCRYPTION_KEY is not set — refusing to store credentials" },
      { status: 400 }
    );
  }

  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid body", details: parsed.error.flatten() },
      { status: 400 }
    );
  }
  const { vendor, baseUrl, label, credentials } = parsed.data;

  // Encrypt before anything touches the database.
  const sealed = encryptCredentials({ ...(baseUrl ? { baseUrl } : {}), ...credentials });

  const db = getDb();
  const existing = await db
    .select({ id: schema.integrations.id })
    .from(schema.integrations)
    .where(eq(schema.integrations.vendor, vendor))
    .limit(1);

  if (existing[0]) {
    await db
      .update(schema.integrations)
      .set({
        credentials: sealed,
        ...(baseUrl ? { baseUrl } : {}),
        ...(label ? { label } : {}),
        status: "connected",
        lastError: null,
      })
      .where(eq(schema.integrations.id, existing[0].id));
    // Audit credential changes (never the credential values themselves).
    const { recordSystemAudit } = await import("@/lib/audit");
    await recordSystemAudit("admin-token", "integration.credentials", `vendor:${vendor}`, {
      updated: true,
    });
    return NextResponse.json({ ok: true, updated: vendor });
  }

  // No row yet for this vendor — create one under the (single-tenant) company.
  const company = await db.select({ id: schema.companies.id }).from(schema.companies).limit(1);
  if (!company[0]) {
    return NextResponse.json({ error: "no company row — seed the database first" }, { status: 400 });
  }
  await db.insert(schema.integrations).values({
    companyId: company[0].id,
    vendor,
    label: label ?? vendor,
    baseUrl: baseUrl ?? null,
    credentials: sealed,
    status: "connected",
  });
  return NextResponse.json({ ok: true, created: vendor });
}
