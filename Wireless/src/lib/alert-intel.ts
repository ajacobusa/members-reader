import type { Alert, Severity } from "@/db/schema";

/**
 * Alert intelligence — turns raw alerts into actionable guidance.
 *
 * Pure, deterministic module (no DB, no network) so it is trivially testable
 * and works identically in mock and Postgres modes:
 *  - PLAYBOOK: per-category root cause + recommended action (the ops runbook).
 *  - Recurrence: same (property, category) seen >= RECURRING_THRESHOLD times
 *    within WINDOW_DAYS marks the alert "recurring".
 *  - Severity rules: recurring alerts escalate one severity step (info →
 *    warning → critical) — chronic problems must not idle at "info". The DB
 *    row is never mutated; the escalated value is an "effective severity"
 *    computed at read time, shown with an explanation.
 *
 * The AI layer (lib/ai.ts) sits on top of this for narrative summaries; this
 * module is the structured ground truth it summarizes.
 */

// How far back two alerts count as "the same problem happening again".
export const WINDOW_DAYS = 30;
// How many occurrences in the window make an issue "recurring".
export const RECURRING_THRESHOLD = 2;

export interface AlertInsight {
  /** Most likely cause, from the category playbook. */
  rootCause: string;
  /** What an engineer should do about it. */
  recommendedAction: string;
  /** Severity after applying escalation rules (>= the stored severity). */
  effectiveSeverity: Severity;
  /** True when severity was bumped by the recurrence rule. */
  escalated: boolean;
  /** True when this (property, category) pair keeps happening. */
  recurring: boolean;
  /** Number of same-category alerts at this property inside the window. */
  occurrences: number;
}

// The runbook: root cause + action per alert category. Single source of truth
// for "what does this alert mean and what do we do" — extend as categories grow.
const PLAYBOOK: Record<string, { cause: string; action: string }> = {
  ap_down: {
    cause: "AP lost power or uplink — PoE failure, switch port down, or hardware fault.",
    action:
      "Check the switch port and PoE budget, power-cycle the AP, and replace the unit if it does not rejoin within 15 minutes.",
  },
  guest_wifi: {
    cause:
      "Captive portal or auth backend failing, or the guest VLAN/WAN is saturated.",
    action:
      "Run the guest login flow end-to-end, check RADIUS/DNS health, verify circuit utilization, and review channel load on the busiest APs.",
  },
  firmware: {
    cause:
      "Access points running behind the recommended firmware train — missing bug and security fixes.",
    action:
      "Schedule a maintenance-window upgrade to the recommended version; stagger by floor or wing to keep coverage up.",
  },
  iot: {
    cause:
      "IoT device unreachable — battery/power loss, a VLAN or NAC policy change, or device fault.",
    action:
      "Verify device power, confirm VLAN and security-group membership, and re-enroll the device on NAC if it was quarantined.",
  },
  rf: {
    cause: "High channel utilization or co-channel interference on 5 GHz.",
    action:
      "Review the RF plan, reduce co-channel interference, and check AP placement and transmit power.",
  },
  uncategorized: {
    cause: "Not yet classified — no category was attached by the source vendor.",
    action: "Triage manually, then add the pattern to the alert playbook.",
  },
};

/** Look up the playbook entry for a category (falls back to uncategorized). */
export function playbookFor(category: string | null): { cause: string; action: string } {
  return PLAYBOOK[category ?? "uncategorized"] ?? PLAYBOOK.uncategorized;
}

/** One severity step up: info → warning → critical (critical stays put). */
export function bumpSeverity(s: Severity): Severity {
  return s === "info" ? "warning" : "critical";
}

/**
 * Enrich one alert with playbook guidance and recurrence-based severity.
 * `allAlerts` is the full alert set (open + resolved) used to count recurrences.
 */
export function enrichAlert(alert: Alert, allAlerts: Alert[]): AlertInsight {
  const { cause, action } = playbookFor(alert.category);

  // Count same-problem occurrences: same property + category, raised within
  // WINDOW_DAYS of this alert (both directions, so history counts too).
  const windowMs = WINDOW_DAYS * 24 * 3600 * 1000;
  const occurrences = allAlerts.filter(
    (a) =>
      a.propertyId === alert.propertyId &&
      (a.category ?? "uncategorized") === (alert.category ?? "uncategorized") &&
      Math.abs(a.raisedAt.getTime() - alert.raisedAt.getTime()) <= windowMs
  ).length;

  const recurring = occurrences >= RECURRING_THRESHOLD;
  // Escalation rule: recurring problems move up one severity step.
  const escalated = recurring && alert.severity !== "critical";
  const effectiveSeverity = escalated ? bumpSeverity(alert.severity) : alert.severity;

  return {
    rootCause: cause,
    recommendedAction: action,
    effectiveSeverity,
    escalated,
    recurring,
    occurrences,
  };
}

// ---------------------------------------------------------------------------
// Grouping — portfolio rollups by any key (property / category / vendor).
// ---------------------------------------------------------------------------

export interface AlertGroup {
  key: string;
  total: number;
  critical: number;
  warning: number;
  info: number;
}

/** Group alerts by an arbitrary key, with per-severity counts, sorted worst-first. */
export function groupAlerts(
  alerts: Alert[],
  keyOf: (a: Alert) => string
): AlertGroup[] {
  const groups = new Map<string, AlertGroup>();
  for (const a of alerts) {
    const key = keyOf(a);
    const g = groups.get(key) ?? { key, total: 0, critical: 0, warning: 0, info: 0 };
    g.total++;
    g[a.severity]++;
    groups.set(key, g);
  }
  // Worst first: most criticals, then most warnings, then volume.
  return [...groups.values()].sort(
    (a, b) => b.critical - a.critical || b.warning - a.warning || b.total - a.total
  );
}

// ---------------------------------------------------------------------------
// Timeline — chronological event stream for the history view.
// ---------------------------------------------------------------------------

export interface TimelineEvent {
  at: Date;
  kind: "raised" | "resolved";
  alert: Alert;
}

/** Flatten alerts into raised/resolved events, newest first. */
export function buildTimeline(alerts: Alert[]): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  for (const a of alerts) {
    events.push({ at: a.raisedAt, kind: "raised", alert: a });
    if (a.resolvedAt) events.push({ at: a.resolvedAt, kind: "resolved", alert: a });
  }
  return events.sort((x, y) => y.at.getTime() - x.at.getTime());
}
