"use server";

import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { getDb, hasDatabase, schema } from "@/db/client";
import { getActor, can } from "@/lib/authz";
import { recordAudit } from "@/lib/audit";

/**
 * Server actions for project workflow: toggling milestones and checklist
 * items. Plain <form> submissions, DB-mode only (mock mode no-ops).
 */

/** Mark a milestone complete (or pending again if it already was). */
export async function toggleMilestone(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "");
  if (!hasDatabase() || !id) return;
  // RBAC: only roles with project.toggle may change project state.
  if (!can((await getActor()).role, "project.toggle")) return;
  const db = getDb();
  const rows = await db
    .select()
    .from(schema.projectMilestones)
    .where(eq(schema.projectMilestones.id, id))
    .limit(1);
  if (!rows[0]) return;
  await db
    .update(schema.projectMilestones)
    .set({ completedAt: rows[0].completedAt ? null : new Date() })
    .where(eq(schema.projectMilestones.id, id));
  await recordAudit("project.milestone", `milestone:${id}`, {
    name: rows[0].name,
    completed: !rows[0].completedAt,
  });
  revalidatePath("/vendors");
}

/** Check / uncheck one cutover or validation checklist item. */
export async function toggleChecklistItem(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "");
  if (!hasDatabase() || !id) return;
  // RBAC: only roles with project.toggle may change project state.
  if (!can((await getActor()).role, "project.toggle")) return;
  const db = getDb();
  const rows = await db
    .select()
    .from(schema.projectChecklist)
    .where(eq(schema.projectChecklist.id, id))
    .limit(1);
  if (!rows[0]) return;
  await db
    .update(schema.projectChecklist)
    .set({ done: rows[0].done === 1 ? 0 : 1 })
    .where(eq(schema.projectChecklist.id, id));
  await recordAudit("project.checklist", `checklist:${id}`, {
    label: rows[0].label,
    done: rows[0].done !== 1,
  });
  revalidatePath("/vendors");
}
