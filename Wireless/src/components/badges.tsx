// `cn` joins CSS class names together (handy when some classes are conditional).
import { cn } from "@/lib/utils";
// These are TypeScript-only types (the `type` keyword) describing the allowed string
// values for severity, device state, risk level, and vendor name. They add no runtime code.
import type {
  Severity,
  DeviceState,
  Risk,
  IntegrationVendorName,
} from "@/db/schema";

/** Human labels for each network vendor — single source for the UI. */
// Maps each internal vendor key (e.g. "meraki") to a nice display name (e.g. "Cisco Meraki").
// `Record<IntegrationVendorName, string>` means every vendor name must have a string label.
export const VENDOR_LABELS: Record<IntegrationVendorName, string> = {
  aruba_central: "Aruba Central",
  meraki: "Cisco Meraki",
  unifi: "Ubiquiti UniFi",
  ruckus: "RUCKUS",
  fortinet: "Fortinet",
  mist: "Juniper Mist",
};

/** Subtle pill naming the vendor that manages a site or device. */
// Shows a small pill with the vendor's name. `vendor` may be null (unknown).
export function VendorBadge({
  vendor,
}: {
  vendor: IntegrationVendorName | null;
}) {
  // If there is no vendor, show a muted dash instead of an empty space.
  if (!vendor) return <span className="text-muted">—</span>;
  return (
    // A rounded "pill" element styled with a subtle background and border.
    <span className="inline-flex items-center rounded-md bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted ring-1 ring-inset ring-border">
      {/* Look up and display the human-friendly label for this vendor. */}
      {VENDOR_LABELS[vendor]}
    </span>
  );
}

// Shared base styles used by the severity/risk badges below, kept in one place
// so every badge has the same shape, padding, and text size.
const base =
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset";

// Badge that color-codes how serious an alert is (critical / warning / info).
export function SeverityBadge({ severity }: { severity: Severity }) {
  // Pick the right color classes for the given severity level.
  const map: Record<Severity, string> = {
    critical: "bg-critical-bg text-critical ring-critical/20",
    warning: "bg-warning-bg text-warning ring-warning/20",
    info: "bg-info-bg text-info ring-info/20",
  };
  // Combine the shared base styles with the color for this severity, and show the text.
  return <span className={cn(base, map[severity])}>{severity}</span>;
}

// Badge showing whether a device is online / degraded / offline, with a colored dot.
export function StatusBadge({ status }: { status: DeviceState }) {
  // For each status we store both the pill color classes (`cls`) and the dot color (`dot`).
  const map: Record<DeviceState, { cls: string; dot: string }> = {
    online: { cls: "bg-good-bg text-good ring-good/20", dot: "bg-good" },
    degraded: { cls: "bg-warning-bg text-warning ring-warning/20", dot: "bg-warning" },
    offline: { cls: "bg-critical-bg text-critical ring-critical/20", dot: "bg-critical" },
  };
  // Pull out the two class strings for the current status using object destructuring.
  const { cls, dot } = map[status];
  return (
    // The pill: shared base styles plus this status's colors.
    <span className={cn(base, cls)}>
      {/* A tiny round dot whose color matches the status (green/amber/red). */}
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
      {status}
    </span>
  );
}

// Badge for the IoT approval lifecycle: green approved, red unapproved (needs
// review — it's the risky state), neutral quarantined (contained).
export function ApprovalBadge({
  approval,
}: {
  approval: "approved" | "unapproved" | "quarantined";
}) {
  const map = {
    approved: "bg-good-bg text-good ring-good/20",
    unapproved: "bg-critical-bg text-critical ring-critical/20",
    quarantined: "bg-surface-2 text-muted ring-border",
  } as const;
  return <span className={cn(base, map[approval])}>{approval}</span>;
}

// Badge showing a risk level (low / medium / high / critical) with matching colors.
export function RiskBadge({ risk }: { risk: Risk }) {
  // Color classes for each risk level; higher risk uses stronger warning/critical colors.
  const map: Record<Risk, string> = {
    low: "bg-good-bg text-good ring-good/20",
    medium: "bg-warning-bg text-warning ring-warning/20",
    high: "bg-critical-bg text-critical ring-critical/20",
    critical: "bg-critical-bg text-critical ring-critical/30",
  };
  // Render the pill with the base styles plus the chosen risk color.
  return <span className={cn(base, map[risk])}>{risk}</span>;
}

/** Colored 0-100 health pill. */
// Displays a numeric health score in a colored pill.
// `band` controls the color (good/fair/poor) and `size` controls how big it is.
// `size = "md"` is a default value used when no size is passed in.
export function HealthScore({
  score,
  band,
  size = "md",
}: {
  score: number;
  band: "good" | "fair" | "poor";
  size?: "sm" | "md" | "lg";
}) {
  // Choose the color classes based on the band: green for good, amber for fair, red for poor.
  // This is a chained ternary: if good -> ... else if fair -> ... else -> poor.
  const color =
    band === "good"
      ? "bg-good-bg text-good ring-good/20"
      : band === "fair"
        ? "bg-warning-bg text-warning ring-warning/20"
        : "bg-critical-bg text-critical ring-critical/20";
  // Choose padding and text size based on the requested size (large / small / medium default).
  const sizing =
    size === "lg"
      ? "text-2xl px-4 py-1.5"
      : size === "sm"
        ? "text-xs px-2 py-0.5"
        : "text-sm px-3 py-1";
  return (
    // The pill combines fixed base styles with the color and sizing chosen above.
    // `tabular-nums` keeps digits the same width so numbers don't jiggle.
    <span
      className={cn(
        "inline-flex items-center rounded-lg font-semibold ring-1 ring-inset tabular-nums",
        color,
        sizing
      )}
    >
      {/* The actual numeric score (0–100). */}
      {score}
    </span>
  );
}
