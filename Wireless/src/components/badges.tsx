import { cn } from "@/lib/utils";
import type {
  Severity,
  DeviceState,
  Risk,
  IntegrationVendorName,
} from "@/db/schema";

/** Human labels for each network vendor — single source for the UI. */
export const VENDOR_LABELS: Record<IntegrationVendorName, string> = {
  aruba_central: "Aruba Central",
  meraki: "Cisco Meraki",
  unifi: "Ubiquiti UniFi",
  ruckus: "RUCKUS",
  fortinet: "Fortinet",
  mist: "Juniper Mist",
};

/** Subtle pill naming the vendor that manages a site or device. */
export function VendorBadge({
  vendor,
}: {
  vendor: IntegrationVendorName | null;
}) {
  if (!vendor) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex items-center rounded-md bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted ring-1 ring-inset ring-border">
      {VENDOR_LABELS[vendor]}
    </span>
  );
}

const base =
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset";

export function SeverityBadge({ severity }: { severity: Severity }) {
  const map: Record<Severity, string> = {
    critical: "bg-critical-bg text-critical ring-critical/20",
    warning: "bg-warning-bg text-warning ring-warning/20",
    info: "bg-info-bg text-info ring-info/20",
  };
  return <span className={cn(base, map[severity])}>{severity}</span>;
}

export function StatusBadge({ status }: { status: DeviceState }) {
  const map: Record<DeviceState, { cls: string; dot: string }> = {
    online: { cls: "bg-good-bg text-good ring-good/20", dot: "bg-good" },
    degraded: { cls: "bg-warning-bg text-warning ring-warning/20", dot: "bg-warning" },
    offline: { cls: "bg-critical-bg text-critical ring-critical/20", dot: "bg-critical" },
  };
  const { cls, dot } = map[status];
  return (
    <span className={cn(base, cls)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
      {status}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: Risk }) {
  const map: Record<Risk, string> = {
    low: "bg-good-bg text-good ring-good/20",
    medium: "bg-warning-bg text-warning ring-warning/20",
    high: "bg-critical-bg text-critical ring-critical/20",
    critical: "bg-critical-bg text-critical ring-critical/30",
  };
  return <span className={cn(base, map[risk])}>{risk}</span>;
}

/** Colored 0-100 health pill. */
export function HealthScore({
  score,
  band,
  size = "md",
}: {
  score: number;
  band: "good" | "fair" | "poor";
  size?: "sm" | "md" | "lg";
}) {
  const color =
    band === "good"
      ? "bg-good-bg text-good ring-good/20"
      : band === "fair"
        ? "bg-warning-bg text-warning ring-warning/20"
        : "bg-critical-bg text-critical ring-critical/20";
  const sizing =
    size === "lg"
      ? "text-2xl px-4 py-1.5"
      : size === "sm"
        ? "text-xs px-2 py-0.5"
        : "text-sm px-3 py-1";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-lg font-semibold ring-1 ring-inset tabular-nums",
        color,
        sizing
      )}
    >
      {score}
    </span>
  );
}
