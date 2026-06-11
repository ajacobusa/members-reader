// Next.js helper that, when called, renders the app's 404 "not found" page.
import { notFound } from "next/navigation";
// Data queries used to build this single-property detail view.
import {
  // Looks up one property by its id (returns null/undefined if missing).
  getProperty,
  // Computes the rolled-up overview (counts + health breakdown) for a property.
  getPropertyOverview,
  // Lists the access points belonging to a property.
  getAccessPoints,
  // Lists the client devices for a property.
  getClients,
  // Lists the IoT devices for a property.
  getIotDevices,
  // Lists the alerts raised for a property.
  getAlerts,
} from "@/lib/queries";
// Shared UI building blocks, including EmptyState for "nothing to show" placeholders.
import { PageHeader, StatCard, Card, Table, Th, Td, EmptyState } from "@/components/ui";
// Various colored badge components used throughout this page.
import {
  HealthScore,
  StatusBadge,
  SeverityBadge,
  RiskBadge,
  VendorBadge,
} from "@/components/badges";
// Utility that turns a timestamp into a friendly "3 hours ago" string.
import { timeAgo } from "@/lib/utils";
// Client component: AI "explain this score" button under the health breakdown.
import { AiExplainScore } from "@/components/ai-explain-score";
// Score history for the before/after trend.
import { getHealthSnapshots } from "@/lib/queries";
import { scoreTrend } from "@/lib/health";
import { Sparkline, DeltaChip } from "@/components/sparkline";

// The detail page for one property. Next.js passes route params (like the id) as props.
export default async function PropertyDetailPage({
  params,
}: {
  // In recent Next.js versions `params` is a Promise that must be awaited.
  params: Promise<{ id: string }>;
}) {
  // Wait for the route params and pull out the property `id` from the URL.
  const { id } = await params;
  // Fetch the property record for that id.
  const property = await getProperty(id);
  // If no property matches this id, show the 404 page and stop rendering.
  if (!property) notFound();

  // Fetch all the related data for this property in parallel for speed.
  const [overview, accessPoints, clients, iotDevices, alerts, allSnapshots] =
    await Promise.all([
      getPropertyOverview(property),
      getAccessPoints(id),
      getClients(id),
      getIotDevices(id),
      getAlerts(id),
      getHealthSnapshots(),
    ]);
  // This property's score history (chronological) and its week-over-week trend.
  const history = allSnapshots.filter((s) => s.propertyId === id);
  const trend = scoreTrend(history, overview.health.score, new Date());

  // Keep only the guest clients (isGuest stored as 1 = true, 0 = false).
  const guests = clients.filter((c) => c.isGuest === 1);
  // Of those guests, count how many failed to connect.
  const guestFailures = guests.filter((c) => c.connectionFailed === 1).length;

  // Fragment wrapper below lets the header, stat grid, and cards render as siblings.
  return (
    <>
      {/* Header showing the property name, its address line, and right-side action badges. */}
      {/* The `actions` prop receives the right-hand area: a vendor badge plus a large health score. */}
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

      {/* Four summary stat cards in a responsive grid. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Online APs over total, with an "N offline" hint; amber if any are offline. */}
        <StatCard
          label="Access points"
          value={`${overview.apCount - overview.apOffline}/${overview.apCount}`}
          hint={`${overview.apOffline} offline`}
          tone={overview.apOffline > 0 ? "warning" : "good"}
        />
        {/* Total connected clients. */}
        <StatCard label="Connected clients" value={overview.clientCount} />
        {/* Successful guest connections over total guests, flagging any failures. */}
        <StatCard
          label="Guest WiFi"
          value={`${guests.length - guestFailures}/${guests.length}`}
          hint={`${guestFailures} connection failures`}
          tone={guestFailures > 0 ? "warning" : "good"}
        />
        {/* Critical alert count, red if greater than zero. */}
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
        {/* Before/after: the score's recent trajectory + week-over-week change. */}
        {history.length >= 2 && (
          <div className="mt-3 flex items-center gap-4">
            <Sparkline points={[...history.map((s) => s.score), overview.health.score]} />
            <div className="text-sm text-muted">
              {trend.weekAgo !== null && (
                <>
                  A week ago this property scored{" "}
                  <span className="font-medium text-foreground">{trend.weekAgo}</span>{" "}
                  <DeltaChip delta={trend.delta} />
                </>
              )}
            </div>
          </div>
        )}
        {/* If there are no deductions show a positive message; otherwise list each deduction. */}
        {overview.health.deductions.length === 0 ? (
          <p className="mt-3 text-sm text-good">No deductions — property is healthy.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {/* One row per deduction: the reason and how many points it cost. */}
            {overview.health.deductions.map((d) => (
              <div key={d.reason} className="flex items-center justify-between text-sm">
                {/* The reason text, with a "×N" multiplier showing how many times it applied. */}
                <span className="text-muted">
                  {d.reason} <span className="text-foreground">×{d.count}</span>
                </span>
                {/* The points subtracted, shown in red with a minus sign. */}
                <span className="font-medium tabular-nums text-critical">−{d.points}</span>
              </div>
            ))}
            {/* Footer row showing the arithmetic: 100 minus total deductions equals the final score. */}
            <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-sm font-semibold">
              <span>Score</span>
              <span className="tabular-nums">100 − {100 - overview.health.score} = {overview.health.score}</span>
            </div>
          </div>
        )}
        {/* AI companion: plain-English explanation of this score on demand. */}
        <AiExplainScore propertyId={property.id} />
      </Card>

      {/* Access points */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Access points
        </div>
        <Table>
          {/* Column headers for the access-points table. */}
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
            {/* When there are no access points, render a single placeholder row. */}
            {accessPoints.length === 0 && (
              <tr><Td className="text-muted">No access points.</Td></tr>
            )}
            {/* Otherwise render one row per access point. */}
            {accessPoints.map((ap) => {
              // `stale` is true when a recommended firmware exists and differs from the installed one.
              const stale =
                ap.firmwareRecommended &&
                ap.firmwareVersion !== ap.firmwareRecommended;
              return (
                <tr key={ap.id} className="hover:bg-surface-2">
                  {/* Access point name. */}
                  <Td className="font-medium">{ap.name}</Td>
                  {/* Hardware model. */}
                  <Td className="text-muted">{ap.model}</Td>
                  {/* Online/offline status badge. */}
                  <Td><StatusBadge status={ap.status} /></Td>
                  {/* Firmware version; amber if stale, with the recommended version appended. */}
                  <Td>
                    <span className={stale ? "text-warning" : "text-muted"}>
                      {ap.firmwareVersion}
                    </span>
                    {stale && (
                      <span className="text-muted"> → {ap.firmwareRecommended}</span>
                    )}
                  </Td>
                  {/* How many clients are connected to this AP. */}
                  <Td className="text-right tabular-nums">{ap.clientCount}</Td>
                  {/* Friendly "time ago" string for when the AP last reported in. */}
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
          {/* Column headers for the IoT devices table. */}
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
            {/* Placeholder row when there are no IoT devices. */}
            {iotDevices.length === 0 && (
              <tr><Td className="text-muted">No IoT devices.</Td></tr>
            )}
            {/* One row per IoT device. */}
            {iotDevices.map((d) => (
              <tr key={d.id} className="hover:bg-surface-2">
                {/* Device name. */}
                <Td className="font-medium">{d.name}</Td>
                {/* Kind of device (camera, sensor, etc.). */}
                <Td className="text-muted">{d.deviceType}</Td>
                {/* The VLAN id the device sits on. */}
                <Td className="text-right tabular-nums">{d.vlan}</Td>
                {/* Which security group/policy applies. */}
                <Td className="text-muted">{d.securityGroup}</Td>
                {/* Online/offline status badge. */}
                <Td><StatusBadge status={d.status} /></Td>
                {/* Risk-level badge (e.g. low/medium/high). */}
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
        {/* Show an empty-state message if there are no alerts; otherwise list them. */}
        {alerts.length === 0 ? (
          <EmptyState message="No alerts for this property." />
        ) : (
          // A divided list, one <li> per alert.
          <ul className="divide-y divide-border">
            {alerts.map((a) => (
              <li key={a.id} className="flex items-start gap-3 px-4 py-3">
                {/* Severity badge on the left. */}
                <SeverityBadge severity={a.severity} />
                {/* Title and optional description in the middle (flex-1 makes it fill space). */}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{a.title}</div>
                  {/* Render the description line only if one exists. */}
                  {a.description && (
                    <div className="text-sm text-muted">{a.description}</div>
                  )}
                </div>
                {/* When the alert was raised, shown on the right. */}
                <div className="shrink-0 text-xs text-muted">{timeAgo(a.raisedAt)}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
