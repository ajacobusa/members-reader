import { notFound } from "next/navigation";
import {
  getProperty,
  getPropertyOverview,
  getAccessPoints,
  getClients,
  getIotDevices,
  getAlerts,
} from "@/lib/queries";
import { PageHeader, StatCard, Card, Table, Th, Td, EmptyState } from "@/components/ui";
import {
  HealthScore,
  StatusBadge,
  SeverityBadge,
  RiskBadge,
  VendorBadge,
} from "@/components/badges";
import { timeAgo } from "@/lib/utils";

export default async function PropertyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const property = await getProperty(id);
  if (!property) notFound();

  const [overview, accessPoints, clients, iotDevices, alerts] = await Promise.all([
    getPropertyOverview(property),
    getAccessPoints(id),
    getClients(id),
    getIotDevices(id),
    getAlerts(id),
  ]);

  const guests = clients.filter((c) => c.isGuest === 1);
  const guestFailures = guests.filter((c) => c.connectionFailed === 1).length;

  return (
    <>
      <PageHeader
        title={property.name}
        subtitle={`${property.address ?? ""} · ${property.city}, ${property.region}`}
        actions={
          <div className="flex items-center gap-3">
            <VendorBadge vendor={property.managedBy} />
            <HealthScore score={overview.health.score} band={overview.health.band} size="lg" />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Access points"
          value={`${overview.apCount - overview.apOffline}/${overview.apCount}`}
          hint={`${overview.apOffline} offline`}
          tone={overview.apOffline > 0 ? "warning" : "good"}
        />
        <StatCard label="Connected clients" value={overview.clientCount} />
        <StatCard
          label="Guest WiFi"
          value={`${guests.length - guestFailures}/${guests.length}`}
          hint={`${guestFailures} connection failures`}
          tone={guestFailures > 0 ? "warning" : "good"}
        />
        <StatCard
          label="Critical alerts"
          value={overview.criticalAlerts}
          tone={overview.criticalAlerts > 0 ? "critical" : "good"}
        />
      </div>

      {/* Health breakdown — why this property scored what it did */}
      <Card className="mt-6 p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">Health score breakdown</div>
          <HealthScore score={overview.health.score} band={overview.health.band} size="sm" />
        </div>
        {overview.health.deductions.length === 0 ? (
          <p className="mt-3 text-sm text-good">No deductions — property is healthy.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {overview.health.deductions.map((d) => (
              <div key={d.reason} className="flex items-center justify-between text-sm">
                <span className="text-muted">
                  {d.reason} <span className="text-foreground">×{d.count}</span>
                </span>
                <span className="font-medium tabular-nums text-critical">−{d.points}</span>
              </div>
            ))}
            <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-sm font-semibold">
              <span>Score</span>
              <span className="tabular-nums">100 − {100 - overview.health.score} = {overview.health.score}</span>
            </div>
          </div>
        )}
      </Card>

      {/* Access points */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Access points
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Model</Th>
              <Th>Status</Th>
              <Th>Firmware</Th>
              <Th className="text-right">Clients</Th>
              <Th className="text-right">Last seen</Th>
            </tr>
          </thead>
          <tbody>
            {accessPoints.length === 0 && (
              <tr><Td className="text-muted">No access points.</Td></tr>
            )}
            {accessPoints.map((ap) => {
              const stale =
                ap.firmwareRecommended &&
                ap.firmwareVersion !== ap.firmwareRecommended;
              return (
                <tr key={ap.id} className="hover:bg-surface-2">
                  <Td className="font-medium">{ap.name}</Td>
                  <Td className="text-muted">{ap.model}</Td>
                  <Td><StatusBadge status={ap.status} /></Td>
                  <Td>
                    <span className={stale ? "text-warning" : "text-muted"}>
                      {ap.firmwareVersion}
                    </span>
                    {stale && (
                      <span className="text-muted"> → {ap.firmwareRecommended}</span>
                    )}
                  </Td>
                  <Td className="text-right tabular-nums">{ap.clientCount}</Td>
                  <Td className="text-right text-muted">{timeAgo(ap.lastSeen)}</Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>

      {/* IoT devices */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          IoT devices
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Device</Th>
              <Th>Type</Th>
              <Th className="text-right">VLAN</Th>
              <Th>Security group</Th>
              <Th>Status</Th>
              <Th>Risk</Th>
            </tr>
          </thead>
          <tbody>
            {iotDevices.length === 0 && (
              <tr><Td className="text-muted">No IoT devices.</Td></tr>
            )}
            {iotDevices.map((d) => (
              <tr key={d.id} className="hover:bg-surface-2">
                <Td className="font-medium">{d.name}</Td>
                <Td className="text-muted">{d.deviceType}</Td>
                <Td className="text-right tabular-nums">{d.vlan}</Td>
                <Td className="text-muted">{d.securityGroup}</Td>
                <Td><StatusBadge status={d.status} /></Td>
                <Td><RiskBadge risk={d.riskLevel} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {/* Alerts */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Recent alerts
        </div>
        {alerts.length === 0 ? (
          <EmptyState message="No alerts for this property." />
        ) : (
          <ul className="divide-y divide-border">
            {alerts.map((a) => (
              <li key={a.id} className="flex items-start gap-3 px-4 py-3">
                <SeverityBadge severity={a.severity} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{a.title}</div>
                  {a.description && (
                    <div className="text-sm text-muted">{a.description}</div>
                  )}
                </div>
                <div className="shrink-0 text-xs text-muted">{timeAgo(a.raisedAt)}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
