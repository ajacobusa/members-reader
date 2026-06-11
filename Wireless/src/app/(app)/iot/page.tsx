// Client-side navigation for property links.
import Link from "next/link";
// Data reads (mock or Postgres, chosen automatically).
import { getIotDevices, getProperties } from "@/lib/queries";
// The IoT segmentation engine: policy findings + rollup counts.
import { assessIotDevices, iotCounts } from "@/lib/iot-intel";
// Shared layout + badge components.
import { PageHeader, StatCard, Card, Table, Th, Td, EmptyState } from "@/components/ui";
import {
  StatusBadge,
  RiskBadge,
  SeverityBadge,
  ApprovalBadge,
} from "@/components/badges";
import { timeAgo } from "@/lib/utils";

// IoT Security page: segmentation findings (the violations that matter) above
// the full inventory with every segmentation field — VLAN, SSID, firewall
// zone, NAC policy, owner, approval, risk, last seen.
export default async function IotPage() {
  const [devices, properties] = await Promise.all([getIotDevices(), getProperties()]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));

  // Run the policy rules and the stat rollup once.
  const findings = assessIotDevices(devices);
  const counts = iotCounts(devices);

  return (
    <>
      <PageHeader
        title="IoT Security"
        subtitle="Segmentation posture for every smart device — locks, cameras, HVAC, kiosks, sensors."
      />

      {/* Rollup stat cards. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="IoT devices" value={counts.total} hint={`${counts.online} online`} />
        <StatCard
          label="Unapproved"
          value={counts.unapproved}
          tone={counts.unapproved > 0 ? "critical" : "good"}
          hint="need review"
        />
        <StatCard
          label="High risk"
          value={counts.highRisk}
          tone={counts.highRisk > 0 ? "warning" : "good"}
        />
        <StatCard
          label="Policy findings"
          value={findings.length}
          tone={findings.some((f) => f.severity === "critical") ? "critical" : findings.length > 0 ? "warning" : "good"}
        />
      </div>

      {/* Segmentation findings — each with the recommended remediation. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Segmentation findings ({findings.length})
        </div>
        {findings.length === 0 ? (
          <EmptyState message="No segmentation violations — all devices approved and correctly segmented." />
        ) : (
          <ul className="divide-y divide-border">
            {findings.map((f, i) => (
              <li key={`${f.device.id}-${i}`} className="px-4 py-3">
                <div className="flex items-start gap-3">
                  <SeverityBadge severity={f.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">
                      {f.device.name}
                      <span className="ml-2 font-normal text-muted">
                        at{" "}
                        <Link
                          href={`/properties/${f.device.propertyId}`}
                          className="hover:text-primary"
                        >
                          {propName.get(f.device.propertyId) ?? "—"}
                        </Link>
                      </span>
                    </div>
                    <div className="mt-0.5 text-sm text-muted">{f.issue}</div>
                    {/* The remediation, in the runbook format. */}
                    <div className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-sm">
                      <span className="font-medium">Recommended action:</span>{" "}
                      <span className="text-muted">{f.action}</span>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Full inventory with every segmentation field. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Device inventory ({devices.length})
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Device</Th>
              <Th>Property</Th>
              <Th>Type</Th>
              <Th>Owner</Th>
              <Th className="text-right">VLAN</Th>
              <Th>SSID</Th>
              <Th>FW zone</Th>
              <Th>NAC policy</Th>
              <Th>Approval</Th>
              <Th>Status</Th>
              <Th>Risk</Th>
              <Th className="text-right">Last seen</Th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.id} className="hover:bg-surface-2">
                <Td className="font-medium">{d.name}</Td>
                <Td>
                  <Link
                    href={`/properties/${d.propertyId}`}
                    className="text-muted hover:text-primary"
                  >
                    {propName.get(d.propertyId) ?? "—"}
                  </Link>
                </Td>
                <Td className="text-muted">{d.deviceType ?? "—"}</Td>
                <Td className="text-muted">{d.owner ?? "—"}</Td>
                <Td className="text-right tabular-nums">{d.vlan ?? "—"}</Td>
                <Td className="text-muted">{d.ssid ?? "—"}</Td>
                <Td className="text-muted">{d.firewallZone ?? "—"}</Td>
                <Td className="text-muted">{d.nacPolicy ?? "—"}</Td>
                <Td><ApprovalBadge approval={d.approval} /></Td>
                <Td><StatusBadge status={d.status} /></Td>
                <Td><RiskBadge risk={d.riskLevel} /></Td>
                <Td className="text-right text-muted">{timeAgo(d.lastSeen)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
