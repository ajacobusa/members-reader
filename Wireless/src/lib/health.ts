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

export const WEIGHTS = {
  criticalAlert: 12,
  warningAlert: 4,
  offlineAp: 10,
  firmwareLagAp: 5, // AP running below its recommended firmware
  guestConnectionFailure: 6,
  iotFailure: 8, // offline IoT device, weighted up by risk
} as const;

export interface HealthInput {
  accessPoints: AccessPoint[];
  clients: Client[];
  iotDevices: IotDevice[];
  alerts: Alert[];
}

export interface HealthDeduction {
  reason: string;
  count: number;
  points: number;
}

export interface HealthResult {
  score: number;
  band: "good" | "fair" | "poor";
  deductions: HealthDeduction[];
}

const isOpen = (a: Alert) => a.status !== "resolved";

export function computeHealth(input: HealthInput): HealthResult {
  const { accessPoints, clients, iotDevices, alerts } = input;
  const deductions: HealthDeduction[] = [];

  const add = (reason: string, count: number, weight: number) => {
    if (count > 0) deductions.push({ reason, count, points: count * weight });
  };

  const criticals = alerts.filter((a) => isOpen(a) && a.severity === "critical").length;
  const warnings = alerts.filter((a) => isOpen(a) && a.severity === "warning").length;
  const offlineAps = accessPoints.filter((ap) => ap.status === "offline").length;
  const firmwareLag = accessPoints.filter(
    (ap) =>
      ap.firmwareRecommended &&
      ap.firmwareVersion &&
      ap.firmwareVersion !== ap.firmwareRecommended
  ).length;
  const guestFailures = clients.filter(
    (c) => c.isGuest === 1 && c.connectionFailed === 1
  ).length;
  const iotFailures = iotDevices.filter((i) => i.status === "offline").length;

  add("Critical alerts", criticals, WEIGHTS.criticalAlert);
  add("Warning alerts", warnings, WEIGHTS.warningAlert);
  add("Offline access points", offlineAps, WEIGHTS.offlineAp);
  add("APs behind recommended firmware", firmwareLag, WEIGHTS.firmwareLagAp);
  add("Guest connection failures", guestFailures, WEIGHTS.guestConnectionFailure);
  add("Offline IoT devices", iotFailures, WEIGHTS.iotFailure);

  const totalPenalty = deductions.reduce((sum, d) => sum + d.points, 0);
  const score = Math.max(0, Math.min(100, 100 - totalPenalty));

  return {
    score,
    band: score >= 85 ? "good" : score >= 60 ? "fair" : "poor",
    deductions,
  };
}
