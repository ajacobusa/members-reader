import type { Alert, Incident, Severity } from "@/db/schema";
import { RECURRING_THRESHOLD } from "./alert-intel";

/**
 * Incident workflow logic — SLA policy and the auto-escalation rules.
 *
 * Pure functions (no DB, no clock reads — `now` is always a parameter) so the
 * rules are unit-testable; lib/sync.ts applies them against Postgres after
 * every sync run, and the UI uses the same helpers for SLA chips.
 */

// SLA targets per severity: how long an incident may stay unresolved.
export const SLA_MINUTES: Record<Severity, number> = {
  critical: 4 * 60, // 4 hours
  warning: 24 * 60, // 1 day
  info: 72 * 60, // 3 days
};

/** The SLA deadline for an incident opened at `openedAt` with `severity`. */
export function slaDueFor(severity: Severity, openedAt: Date): Date {
  return new Date(openedAt.getTime() + SLA_MINUTES[severity] * 60_000);
}

export interface SlaState {
  dueAt: Date | null;
  /** True when the deadline has passed and the incident isn't resolved. */
  breached: boolean;
  /** Minutes remaining (negative when past due); null without a deadline. */
  minutesLeft: number | null;
}

/** Where an incident stands against its SLA at time `now`. */
export function slaState(incident: Incident, now: Date): SlaState {
  if (!incident.slaDueAt) return { dueAt: null, breached: false, minutesLeft: null };
  const minutesLeft = Math.round((incident.slaDueAt.getTime() - now.getTime()) / 60_000);
  const active = incident.status !== "resolved";
  return {
    dueAt: incident.slaDueAt,
    breached: active && minutesLeft < 0,
    minutesLeft,
  };
}

/** Human SLA chip text: "SLA: 3h 20m left" or "SLA breached 2h ago". */
export function formatSla(s: SlaState): string {
  if (s.minutesLeft === null) return "No SLA";
  const abs = Math.abs(s.minutesLeft);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  const span = h > 0 ? `${h}h ${m}m` : `${m}m`;
  return s.minutesLeft >= 0 ? `SLA: ${span} left` : `SLA breached ${span} ago`;
}

// ---------------------------------------------------------------------------
// Auto-escalation rules (applied by the sync automation)
// ---------------------------------------------------------------------------

export interface RecurringCandidate {
  propertyId: string;
  category: string;
  count: number;
  /** Highest severity among the group's open alerts. */
  severity: Severity;
  /** Newest alert in the group — the incident links back to it. */
  newestAlertId: string;
}

const RANK: Record<Severity, number> = { critical: 0, warning: 1, info: 2 };

/**
 * Rule 1 — auto-create: find (property, category) groups with at least
 * RECURRING_THRESHOLD open alerts and no open incident covering them.
 */
export function findRecurringWithoutIncident(
  alerts: Alert[],
  incidents: Incident[]
): RecurringCandidate[] {
  // Group open alerts by property + category.
  const groups = new Map<string, Alert[]>();
  for (const a of alerts) {
    if (a.status === "resolved" || !a.category) continue;
    const key = `${a.propertyId}::${a.category}`;
    groups.set(key, [...(groups.get(key) ?? []), a]);
  }

  // An open incident with the same property + category already covers a group.
  const covered = new Set(
    incidents
      .filter((i) => i.status !== "resolved" && i.propertyId && i.category)
      .map((i) => `${i.propertyId}::${i.category}`)
  );

  const out: RecurringCandidate[] = [];
  for (const [key, group] of groups) {
    if (group.length < RECURRING_THRESHOLD || covered.has(key)) continue;
    const [propertyId, category] = key.split("::");
    const severity = group.reduce<Severity>(
      (worst, a) => (RANK[a.severity] < RANK[worst] ? a.severity : worst),
      "info"
    );
    const newest = group.reduce((n, a) => (a.raisedAt > n.raisedAt ? a : n));
    out.push({ propertyId, category, count: group.length, severity, newestAlertId: newest.id });
  }
  return out;
}

/** Rule 2 — auto-escalate: open/investigating incidents past their SLA. */
export function findSlaBreaches(incidents: Incident[], now: Date): Incident[] {
  return incidents.filter(
    (i) =>
      (i.status === "open" || i.status === "investigating") &&
      slaState(i, now).breached
  );
}

/** Title used for auto-created incidents (also the human-readable marker). */
export function recurringIncidentTitle(category: string, propertyName: string): string {
  return `Recurring ${category.replace(/_/g, " ")} issues — ${propertyName}`;
}
