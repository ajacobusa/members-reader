// Pull in the data shapes (TypeScript types only, no runtime code) for the four
// inputs the health score is computed from. The `type` keyword means these are
// erased at build time — they only help the compiler check our code.
import type { AccessPoint, Alert, Client, IotDevice } from "@/db/schema";

/**
 * Property health score (0-100), per the framework formula:
 *
 *   score = 100 - critical alerts - offline APs - firmware risk
 *               - guest complaints - IoT failures
 *
 * Kept deliberately simple and transparent: every deduction is itemized so the
 * UI can show *why* a property scored what it did. Tune the weights in WEIGHTS.
 */

// How many points each *single occurrence* of a problem deducts from the score.
// `as const` freezes these into exact literal values (so e.g. criticalAlert is the
// number 12, not just "some number") — the single place to tune the scoring.
export const WEIGHTS = {
  criticalAlert: 12, // each unresolved critical alert costs 12 points
  warningAlert: 4, // each unresolved warning alert costs 4 points
  offlineAp: 10, // each access point that is fully down costs 10 points
  firmwareLagAp: 5, // AP running below its recommended firmware
  guestConnectionFailure: 6, // each guest that failed to connect costs 6 points
  iotFailure: 8, // offline IoT device, weighted up by risk
  unapprovedIot: 7, // each unapproved IoT device on the network (segmentation risk)
} as const;

// The bundle of raw data the scorer needs: all the devices, clients, and alerts
// for one property. Each field is an array of rows of that type.
export interface HealthInput {
  accessPoints: AccessPoint[];
  clients: Client[];
  iotDevices: IotDevice[];
  alerts: Alert[];
}

// One itemized line of "why points were lost": a human reason, how many things
// triggered it, and the total points removed for that line.
export interface HealthDeduction {
  reason: string;
  count: number;
  points: number;
}

// The final output: the 0-100 number, a coarse text band for coloring the UI,
// and the full breakdown of deductions that produced the score.
export interface HealthResult {
  score: number;
  band: "good" | "fair" | "poor";
  deductions: HealthDeduction[];
}

// Tiny helper: an alert "counts" as a live problem unless it has been resolved.
const isOpen = (a: Alert) => a.status !== "resolved";

// The main entry point: given one property's data, return its health score + breakdown.
export function computeHealth(input: HealthInput): HealthResult {
  // Destructure the four input arrays out of the bundle for easier access below.
  const { accessPoints, clients, iotDevices, alerts } = input;
  // We'll collect each "points lost" line here as we discover problems.
  const deductions: HealthDeduction[] = [];

  // Convenience helper to record a deduction line. It multiplies how many problems
  // (count) by the per-problem weight, and only records the line if count > 0 so we
  // don't clutter the breakdown with zero-impact rows.
  const add = (reason: string, count: number, weight: number) => {
    if (count > 0) deductions.push({ reason, count, points: count * weight });
  };

  // Count unresolved critical alerts (open AND severity === "critical").
  const criticals = alerts.filter((a) => isOpen(a) && a.severity === "critical").length;
  // Count unresolved warning alerts.
  const warnings = alerts.filter((a) => isOpen(a) && a.severity === "warning").length;
  // Count access points whose status is fully "offline".
  const offlineAps = accessPoints.filter((ap) => ap.status === "offline").length;
  // Count APs running firmware that lags the recommended version. We require BOTH
  // fields to be present (truthy) so a missing/unknown version doesn't false-trigger,
  // then flag any AP whose installed version differs from the recommended one.
  const firmwareLag = accessPoints.filter(
    (ap) =>
      ap.firmwareRecommended &&
      ap.firmwareVersion &&
      ap.firmwareVersion !== ap.firmwareRecommended
  ).length;
  // Count guest clients that failed to connect. isGuest/connectionFailed are stored
  // as 0/1 integers (SQLite-style booleans), so we compare against 1.
  const guestFailures = clients.filter(
    (c) => c.isGuest === 1 && c.connectionFailed === 1
  ).length;
  // Count IoT devices that are offline.
  const iotFailures = iotDevices.filter((i) => i.status === "offline").length;
  // Count IoT devices that haven't been approved — each is a segmentation risk
  // (quarantined devices are contained, so they don't deduct here).
  const unapprovedIot = iotDevices.filter((i) => i.approval === "unapproved").length;

  // Turn each count above into a deduction line using its matching weight.
  add("Critical alerts", criticals, WEIGHTS.criticalAlert);
  add("Warning alerts", warnings, WEIGHTS.warningAlert);
  add("Offline access points", offlineAps, WEIGHTS.offlineAp);
  add("APs behind recommended firmware", firmwareLag, WEIGHTS.firmwareLagAp);
  add("Guest connection failures", guestFailures, WEIGHTS.guestConnectionFailure);
  add("Offline IoT devices", iotFailures, WEIGHTS.iotFailure);
  add("Unapproved IoT devices", unapprovedIot, WEIGHTS.unapprovedIot);

  // Sum every line's points into one total penalty (reduce walks the array adding up `.points`).
  const totalPenalty = deductions.reduce((sum, d) => sum + d.points, 0);
  // Start from a perfect 100 and subtract the penalty, then clamp into the 0-100 range:
  // Math.min(100, ...) caps the top, Math.max(0, ...) prevents going negative.
  const score = Math.max(0, Math.min(100, 100 - totalPenalty));

  // Return the score, a coarse band (85+ good, 60-84 fair, below 60 poor) for UI coloring,
  // and the full itemized deductions so the UI can explain the number.
  return {
    score,
    band: score >= 85 ? "good" : score >= 60 ? "fair" : "poor",
    deductions,
  };
}

// ---------------------------------------------------------------------------
// Score trend — the before/after story (pure, testable).
// ---------------------------------------------------------------------------

export interface ScoreTrend {
  /** The score roughly `days` ago (closest snapshot), or null without history. */
  weekAgo: number | null;
  /** current − weekAgo: negative = the property got worse. Null without history. */
  delta: number | null;
}

/**
 * Compare the current score against history: pick the snapshot closest to
 * `now − days` and report the change. Powers the dashboard Δ column,
 * property sparkline captions, and trend-aware AI prompts.
 */
export function scoreTrend(
  snapshots: { score: number; at: Date }[],
  currentScore: number,
  now: Date,
  days = 7
): ScoreTrend {
  if (snapshots.length === 0) return { weekAgo: null, delta: null };
  const target = now.getTime() - days * 86_400_000;
  // The snapshot whose timestamp is nearest the target moment.
  const closest = snapshots.reduce((best, s) =>
    Math.abs(s.at.getTime() - target) < Math.abs(best.at.getTime() - target) ? s : best
  );
  return { weekAgo: closest.score, delta: currentScore - closest.score };
}
