"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { getDb, hasDatabase, schema } from "@/db/client";
import { slaDueFor } from "@/lib/incidents";
import { getActor, can } from "@/lib/authz";
import { recordAudit } from "@/lib/audit";
import { incidentStatus, type Severity } from "@/db/schema";

/**
 * Server actions for the ticketing workflow. Each is invoked from a plain
 * <form> (no client JS needed) and re-renders the affected pages.
 *
 * Writes require a database; in mock mode the actions no-op back to the page
 * (the UI shows a "connect a database" hint in that case).
 */

/** Create an incident from an alert; marks the alert acknowledged. */
export async function createIncidentFromAlert(formData: FormData): Promise<void> {
  const alertId = String(formData.get("alertId") ?? "");
  if (!hasDatabase() || !alertId) redirect("/incidents");
  // RBAC: only roles with incident.create may open incidents.
  if (!can((await getActor()).role, "incident.create")) redirect("/incidents");

  const db = getDb();
  const rows = await db.select().from(schema.alerts).where(eq(schema.alerts.id, alertId)).limit(1);
  const alert = rows[0];
  if (!alert) redirect("/incidents");

  const now = new Date();
  // The incident inherits the alert's property/severity/category; the SLA
  // deadline follows the severity policy from lib/incidents.ts.
  const inserted = await db
    .insert(schema.incidents)
    .values({
      propertyId: alert.propertyId,
      title: alert.title,
      summary: alert.description,
      status: "open",
      severity: alert.severity as Severity,
      category: alert.category,
      alertId: alert.id,
      slaDueAt: slaDueFor(alert.severity as Severity, now),
      openedAt: now,
    })
    .returning({ id: schema.incidents.id });
  await db.insert(schema.incidentNotes).values({
    incidentId: inserted[0].id,
    author: "ops",
    body: `Created from alert "${alert.title}".`,
  });
  // Acknowledge the source alert so it stops counting as untriaged.
  await db
    .update(schema.alerts)
    .set({ status: "acknowledged" })
    .where(eq(schema.alerts.id, alert.id));

  // Audit: who created which incident from which alert.
  await recordAudit("incident.create", `incident:${inserted[0].id}`, {
    fromAlert: alert.id,
    title: alert.title,
  });

  revalidatePath("/incidents");
  revalidatePath("/alerts");
  redirect("/incidents");
}

/** Update owner and/or workflow status; resolving stamps resolvedAt. */
export async function updateIncident(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "");
  const owner = String(formData.get("owner") ?? "").trim();
  const status = String(formData.get("status") ?? "");
  if (!hasDatabase() || !id) return;
  // RBAC: only roles with incident.update may change workflow state.
  if (!can((await getActor()).role, "incident.update")) return;
  // Validate the status against the enum before writing.
  if (!(incidentStatus.enumValues as string[]).includes(status)) return;

  const db = getDb();
  // Read the current row first so the audit entry can carry before → after.
  const before = (
    await db.select().from(schema.incidents).where(eq(schema.incidents.id, id)).limit(1)
  )[0];
  if (!before) return;

  await db
    .update(schema.incidents)
    .set({
      owner: owner || null,
      status: status as (typeof incidentStatus.enumValues)[number],
      // Stamp/clear the resolution time as the status crosses "resolved".
      resolvedAt: status === "resolved" ? new Date() : null,
    })
    .where(eq(schema.incidents.id, id));

  // Audit with change history: only the fields that actually changed.
  const changes: Record<string, unknown> = {};
  if (before.status !== status) changes.status = { from: before.status, to: status };
  if ((before.owner ?? "") !== owner) changes.owner = { from: before.owner, to: owner || null };
  if (Object.keys(changes).length > 0) {
    await recordAudit("incident.update", `incident:${id}`, changes);
  }

  revalidatePath("/incidents");
}

/** Append a work-log note to an incident. */
export async function addIncidentNote(formData: FormData): Promise<void> {
  const incidentId = String(formData.get("incidentId") ?? "");
  const body = String(formData.get("body") ?? "").trim();
  if (!hasDatabase() || !incidentId || !body) return;
  // RBAC + identity: notes are authored as the current actor.
  const actor = await getActor();
  if (!can(actor.role, "incident.note")) return;
  const author = String(formData.get("author") ?? "").trim() || actor.name;

  await getDb().insert(schema.incidentNotes).values({ incidentId, author, body });
  await recordAudit("incident.note", `incident:${incidentId}`, { author });
  revalidatePath("/incidents");
}
