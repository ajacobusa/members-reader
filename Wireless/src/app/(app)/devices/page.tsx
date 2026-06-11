// Next.js link component for fast client-side navigation.
import Link from "next/link";
// Queries: all access points, all IoT devices, and all properties (portfolio-wide, no id filter).
import {
  getAccessPoints,
  getIotDevices,
  getProperties,
} from "@/lib/queries";
// Shared layout and table UI pieces.
import { PageHeader, Card, Table, Th, Td } from "@/components/ui";
// Badges for device status, IoT risk level, and managing vendor.
import { StatusBadge, RiskBadge, VendorBadge } from "@/components/badges";
// Utility to format timestamps as "time ago".
import { timeAgo } from "@/lib/utils";

// Server component listing every device (APs and IoT) across all properties.
export default async function DevicesPage() {
  // Fetch access points, IoT devices, and properties in parallel.
  const [accessPoints, iotDevices, properties] = await Promise.all([
    getAccessPoints(),
    getIotDevices(),
    getProperties(),
  ]);
  // Build a lookup Map from property id -> property name for quick label resolution.
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  // Build a lookup Map from property id -> managing vendor.
  const propVendor = new Map(properties.map((p) => [p.id, p.managedBy]));
  // Small helper that renders a link to a property, using the name Map (falling back to "—").
  const link = (propertyId: string) => (
    <Link href={`/properties/${propertyId}`} className="text-muted hover:text-primary">
      {propName.get(propertyId) ?? "—"}
    </Link>
  );

  // Fragment wrapper lets the two cards (APs and IoT) render as siblings.
  return (
    <>
      {/* Page title and subtitle. */}
      <PageHeader
        title="Device Inventory"
        subtitle="All access points and IoT devices across the portfolio."
      />

      {/* First card: the access-points table. */}
      <Card>
        {/* Card heading showing the total number of access points. */}
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Access points ({accessPoints.length})
        </div>
        <Table>
          {/* Column headers. */}
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Property</Th>
              <Th>Network</Th>
              <Th>Model</Th>
              <Th>Status</Th>
              <Th>Firmware</Th>
              <Th className="text-right">Clients</Th>
              <Th className="text-right">Last seen</Th>
            </tr>
          </thead>
          <tbody>
            {/* One row per access point. */}
            {accessPoints.map((ap) => {
              // True when installed firmware differs from the recommended version.
              const stale =
                ap.firmwareRecommended && ap.firmwareVersion !== ap.firmwareRecommended;
              return (
                <tr key={ap.id} className="hover:bg-surface-2">
                  {/* AP name. */}
                  <Td className="font-medium">{ap.name}</Td>
                  {/* Linked property name (via the `link` helper above). */}
                  <Td>{link(ap.propertyId)}</Td>
                  {/* Vendor badge looked up from the property's managing vendor. */}
                  <Td><VendorBadge vendor={propVendor.get(ap.propertyId) ?? null} /></Td>
                  {/* Hardware model. */}
                  <Td className="text-muted">{ap.model}</Td>
                  {/* Online/offline status badge. */}
                  <Td><StatusBadge status={ap.status} /></Td>
                  {/* Firmware version, amber when stale, with the recommended version appended. */}
                  <Td className={stale ? "text-warning" : "text-muted"}>
                    {ap.firmwareVersion}
                    {stale && <span className="text-muted"> → {ap.firmwareRecommended}</span>}
                  </Td>
                  {/* Connected client count. */}
                  <Td className="text-right tabular-nums">{ap.clientCount}</Td>
                  {/* Last-seen time, humanized. */}
                  <Td className="text-right text-muted">{timeAgo(ap.lastSeen)}</Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>

      {/* Second card: the IoT devices table. */}
      <Card className="mt-6">
        {/* Card heading with the IoT device count. */}
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          IoT devices ({iotDevices.length})
        </div>
        <Table>
          {/* Column headers. */}
          <thead>
            <tr>
              <Th>Device</Th>
              <Th>Property</Th>
              <Th>Type</Th>
              <Th>Vendor</Th>
              <Th className="text-right">VLAN</Th>
              <Th>Status</Th>
              <Th>Risk</Th>
            </tr>
          </thead>
          <tbody>
            {/* One row per IoT device. */}
            {iotDevices.map((d) => (
              <tr key={d.id} className="hover:bg-surface-2">
                {/* Device name. */}
                <Td className="font-medium">{d.name}</Td>
                {/* Linked property name. */}
                <Td>{link(d.propertyId)}</Td>
                {/* Device type. */}
                <Td className="text-muted">{d.deviceType}</Td>
                {/* The device's own manufacturer/vendor (a plain string, not a badge). */}
                <Td className="text-muted">{d.vendor}</Td>
                {/* VLAN id. */}
                <Td className="text-right tabular-nums">{d.vlan}</Td>
                {/* Online/offline status badge. */}
                <Td><StatusBadge status={d.status} /></Td>
                {/* Risk-level badge. */}
                <Td><RiskBadge risk={d.riskLevel} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
