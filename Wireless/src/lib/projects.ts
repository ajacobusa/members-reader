import type { ProjectMilestone, ProjectChecklistItem } from "@/db/schema";

/**
 * Vendor/project management helpers — pure functions shared by the UI and
 * verification script (same pattern as alert-intel / incidents).
 */

// How far ahead a contract end counts as "expiring soon".
export const CONTRACT_WARNING_DAYS = 90;

/** True when `end` lands within CONTRACT_WARNING_DAYS of `now` (and not past). */
export function contractExpiringSoon(end: Date | null, now: Date): boolean {
  if (!end) return false;
  const diffDays = (end.getTime() - now.getTime()) / 86_400_000;
  return diffDays >= 0 && diffDays <= CONTRACT_WARNING_DAYS;
}

/** True when the contract end has already passed. */
export function contractExpired(end: Date | null, now: Date): boolean {
  return Boolean(end && end.getTime() < now.getTime());
}

export interface Progress {
  done: number;
  total: number;
  /** 0-100, rounded; 0 when there is nothing to count. */
  pct: number;
}

/** Milestone completion progress for one project. */
export function milestoneProgress(milestones: ProjectMilestone[]): Progress {
  const total = milestones.length;
  const done = milestones.filter((m) => m.completedAt !== null).length;
  return { done, total, pct: total === 0 ? 0 : Math.round((done / total) * 100) };
}

/** Checklist completion progress for one project phase. */
export function checklistProgress(items: ProjectChecklistItem[]): Progress {
  const total = items.length;
  const done = items.filter((i) => i.done === 1).length;
  return { done, total, pct: total === 0 ? 0 : Math.round((done / total) * 100) };
}
