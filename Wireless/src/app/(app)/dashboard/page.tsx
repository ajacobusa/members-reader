import Link from "next/link";
import {
  getPortfolio,
  getAlertCounts,
  getRecurringIssues,
} from "@/lib/queries";
import { PageHeader, StatCard, Card, Table, Th, Td } from "@/components/ui";
import { HealthScore, SeverityBadge } from "@/components/badges";

export default async function DashboardPage() {
  const [portfolio, alertCounts, recurring] = await Promise.all([
    getPortfolio(),
    getAlertCounts(),
    getRecurringIssues(),
  ]);

  const totalAps = portfolio.reduce((n, p) => n + p.apCount, 0);
  const offlineAps = portfolio.reduce((n, p) => n + p.apOffline, 0);
  const avgHealth = Math.round(
    portfolio.reduce((n, p) => n + p.health.score, 0) / (portfolio.length || 1)
  );

  return (
    <>
      <PageHeader
        title="Portfolio Dashboard"
        subtitle="Health and alerts across every property. Worst-performing sites surface first."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Properties" value={portfolio.length} />
        <StatCard
          label="Avg health"
          value={avgHealth}
          tone={avgHealth >= 85 ? "good" : avgHealth >= 60 ? "warning" : "critical"}
        />
        <StatCard
          label="APs offline"
          value={`${offlineAps} / ${totalAps}`}
          tone={offlineAps > 0 ? "warning" : "good"}
        />
        <StatCard
          label="Critical alerts"
          value={alertCounts.critical}
          tone={alertCounts.critical > 0 ? "critical" : "good"}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="border-b border-border px-4 py-3 text-sm font-semibold">
            Property health
          </div>
          <Table>
            <thead>
              <tr>
                <Th>Property</Th>
                <Th>Location</Th>
                <Th className="text-right">APs</Th>
                <Th className="text-right">Open alerts</Th>
                <Th className="text-right">Health</Th>
              </tr>
            </thead>
            <tbody>
              {portfolio.map(({ property, health, apCount, apOffline, openAlerts, criticalAlerts }) => (
                <tr key={property.id} className="hover:bg-surface-2">
                  <Td>
                    <Link
                      href={`/properties/${property.id}`}
                      className="font-medium text-foreground hover:text-primary"
                    >
                      {property.name}
                    </Link>
                  </Td>
                  <Td className="text-muted">
                    {property.city}, {property.region}
                  </Td>
                  <Td className="text-right tabular-nums">
                    {apCount - apOffline}/{apCount}
                  </Td>
                  <Td className="text-right tabular-nums">
                    {openAlerts}
                    {criticalAlerts > 0 && (
                      <span className="ml-1 text-critical">({criticalAlerts} crit)</span>
                    )}
                  </Td>
                  <Td className="text-right">
                    <HealthScore score={health.score} band={health.band} size="sm" />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <div className="space-y-6">
          <Card className="p-4">
            <div className="text-sm font-semibold">Alerts by severity</div>
            <div className="mt-3 space-y-2">
              <SeverityRow label="Critical" count={alertCounts.critical} severity="critical" />
              <SeverityRow label="Warning" count={alertCounts.warning} severity="warning" />
              <SeverityRow label="Info" count={alertCounts.info} severity="info" />
            </div>
            <Link
              href="/alerts"
              className="mt-4 inline-block text-sm font-medium text-primary hover:underline"
            >
              View all alerts →
            </Link>
          </Card>

          <Card className="p-4">
            <div className="text-sm font-semibold">Recurring issues</div>
            <div className="mt-3 space-y-2">
              {recurring.slice(0, 5).map((r) => (
                <div key={r.category} className="flex items-center justify-between text-sm">
                  <span className="capitalize text-muted">
                    {r.category.replace(/_/g, " ")}
                  </span>
                  <span className="font-medium tabular-nums">{r.count}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function SeverityRow({
  label,
  count,
  severity,
}: {
  label: string;
  count: number;
  severity: "critical" | "warning" | "info";
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm">
        <SeverityBadge severity={severity} />
        <span className="text-muted">{label}</span>
      </div>
      <span className="text-lg font-semibold tabular-nums">{count}</span>
    </div>
  );
}
