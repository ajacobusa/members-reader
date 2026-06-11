import type { IotDevice, Severity } from "@/db/schema";

/**
 * IoT segmentation intelligence — pure, deterministic checks over the IoT
 * inventory (no DB, no network; same testable pattern as alert-intel).
 *
 * The rules encode hotel network-security policy:
 *  1. An UNAPPROVED device OFF the IoT segment (staff/corp network) is the
 *     critical case — an unknown device with a path to sensitive systems.
 *  2. An unapproved device on the IoT segment still needs review.
 *  3. A high-risk device that is offline may be tampered with or failing.
 *  4. An approved device with no firewall zone is a policy gap.
 *  5. Quarantined devices are contained but awaiting review.
 */

export interface IotFinding {
  device: IotDevice;
  severity: Severity;
  issue: string;
  action: string;
}

/** True when the device's segment looks like the dedicated IoT network. */
export function onIotSegment(d: IotDevice): boolean {
  const hay = `${d.securityGroup ?? ""} ${d.firewallZone ?? ""} ${d.ssid ?? ""}`.toLowerCase();
  return hay.includes("iot");
}

/** Run every segmentation rule over the inventory; worst findings first. */
export function assessIotDevices(devices: IotDevice[]): IotFinding[] {
  const findings: IotFinding[] = [];

  for (const d of devices) {
    // Rule 1 — the critical detection: unknown/unapproved device on a
    // non-IoT (staff/corp) network segment.
    if (d.approval === "unapproved" && !onIotSegment(d)) {
      findings.push({
        device: d,
        severity: "critical",
        issue: `Unknown IoT device detected on ${d.ssid ?? d.securityGroup ?? "a non-IoT"} network.`,
        action: "Move to the IoT VLAN or quarantine via NAC, then identify the owner before approving.",
      });
      continue; // the critical finding covers this device
    }
    // Rule 2 — unapproved but at least correctly segmented.
    if (d.approval === "unapproved") {
      findings.push({
        device: d,
        severity: "warning",
        issue: "Unapproved device on the IoT segment.",
        action: "Review the device, assign an owner, and approve or quarantine it.",
      });
    }
    // Rule 3 — high-risk hardware that has gone dark.
    if (d.status === "offline" && (d.riskLevel === "high" || d.riskLevel === "critical")) {
      findings.push({
        device: d,
        severity: "critical",
        issue: "High-risk device is offline — possible tamper or failure.",
        action: "Verify power and physical access; inspect the device and its switch port.",
      });
    }
    // Rule 4 — approved device missing a firewall zone assignment.
    if (d.approval === "approved" && !d.firewallZone) {
      findings.push({
        device: d,
        severity: "info",
        issue: "Approved device has no firewall zone assigned.",
        action: "Map the device's VLAN to a firewall zone so policy applies.",
      });
    }
    // Rule 5 — quarantined: contained, but don't forget it.
    if (d.approval === "quarantined") {
      findings.push({
        device: d,
        severity: "info",
        issue: "Device is quarantined awaiting review.",
        action: "Complete the investigation, then approve or remove the device.",
      });
    }
  }

  // Worst first: critical, then warning, then info.
  const order: Record<Severity, number> = { critical: 0, warning: 1, info: 2 };
  return findings.sort((a, b) => order[a.severity] - order[b.severity]);
}

/** Quick rollup counts for stat cards. */
export function iotCounts(devices: IotDevice[]) {
  return {
    total: devices.length,
    online: devices.filter((d) => d.status === "online").length,
    unapproved: devices.filter((d) => d.approval === "unapproved").length,
    quarantined: devices.filter((d) => d.approval === "quarantined").length,
    highRisk: devices.filter((d) => d.riskLevel === "high" || d.riskLevel === "critical").length,
  };
}
