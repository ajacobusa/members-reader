import "server-only";
import { desc } from "drizzle-orm";
import { getDb, hasDatabase, schema } from "@/db/client";
import { getActor, type Actor } from "@/lib/authz";
import type { AuditEntry } from "@/db/schema";

/**
 * Audit trail — one call per meaningful write. Best-effort by design: auditing
 * must never break the action it records (failures are swallowed), and it
 * no-ops in mock mode where there is no database.
 */

/** Record an action by the current request's actor. */
export async function recordAudit(
  action: string,
  target?: string,
  details?: Record<string, unknown>
): Promise<void> {
  if (!hasDatabase()) return;
  try {
    const actor = await getActor();
    await writeEntry(actor, action, target, details);
  } catch {
    // Auditing is never allowed to fail the underlying operation.
  }
}

/** Record an action by a machine identity (admin token, webhook, automation). */
export async function recordSystemAudit(
  actorId: string,
  action: string,
  target?: string,
  details?: Record<string, unknown>
): Promise<void> {
  if (!hasDatabase()) return;
  try {
    await getDb().insert(schema.auditLog).values({
      actorId,
      actorName: actorId,
      role: "system",
      action,
      target: target ?? null,
      details: details ?? null,
    });
  } catch {
    // Never fail the caller.
  }
}

async function writeEntry(
  actor: Actor,
  action: string,
  target?: string,
  details?: Record<string, unknown>
): Promise<void> {
  await getDb().insert(schema.auditLog).values({
    actorId: actor.userId,
    actorName: actor.name,
    role: actor.role,
    action,
    target: target ?? null,
    details: details ?? null,
  });
}

/** Most recent audit entries for the audit page (newest first). */
export async function getAuditEntries(limit = 50): Promise<AuditEntry[]> {
  if (!hasDatabase()) return [];
  return getDb().select().from(schema.auditLog).orderBy(desc(schema.auditLog.at)).limit(limit);
}
