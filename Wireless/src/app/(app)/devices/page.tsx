import Link from "next/link";
import {
  getAccessPoints,
  getIotDevices,
  getProperties,
} from "@/lib/queries";
import { PageHeader, Card, Table, Th, Td } from "@/components/ui";
import { StatusBadge, RiskBadge, VendorBadge } from "@/components/badges";
import { timeAgo } from "@/lib/utils";

export default async function DevicesPage() {
  const [accessPoints, iotDevices, properties] = await Promise.all([
    getAccessPoints(),
    getIotDevices(),
    getProperties(),
  ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  const propVendor = new Map(properties.map((p) => [p.id, p.managedBy]));
  const link = (propertyId: string) => (
    <Link href={`/properties/${propertyId}`} className="text-muted hover:text-primary">
      {propName.get(propertyId) ?? "—"}
    </Link>
  );

  return (
    <>
      <PageHeader
        title="Device Inventory"
        subtitle="All access points and IoT devices across the portfolio."
      />

      <Card>
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Access points ({accessPoints.length})
        </div>
        <Table>
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
            {accessPoints.map((ap) => {
              const stale =
                ap.firmwareRecommended && ap.firmwareVersion !== ap.firmwareRecommended;
              return (
                <tr key={ap.id} className="hover:bg-surface-2">
                  <Td className="font-medium">{ap.name}</Td>
                  <Td>{link(ap.propertyId)}</Td>
                  <Td><VendorBadge vendor={propVendor.get(ap.propertyId) ?? null} /></Td>
                  <Td className="text-muted">{ap.model}</Td>
                  <Td><StatusBadge status={ap.status} /></Td>
                  <Td className={stale ? "text-warning" : "text-muted"}>
                    {ap.firmwareVersion}
                    {stale && <span className="text-muted"> → {ap.firmwareRecommended}</span>}
                  </Td>
                  <Td className="text-right tabular-nums">{ap.clientCount}</Td>
                  <Td className="text-right text-muted">{timeAgo(ap.lastSeen)}</Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>

      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          IoT devices ({iotDevices.length})
        </div>
        <Table>
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
            {iotDevices.map((d) => (
              <tr key={d.id} className="hover:bg-surface-2">
                <Td className="font-medium">{d.name}</Td>
                <Td>{link(d.propertyId)}</Td>
                <Td className="text-muted">{d.deviceType}</Td>
                <Td className="text-muted">{d.vendor}</Td>
                <Td className="text-right tabular-nums">{d.vlan}</Td>
                <Td><StatusBadge status={d.status} /></Td>
                <Td><RiskBadge risk={d.riskLevel} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
