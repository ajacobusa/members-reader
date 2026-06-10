import Link from "next/link";
import { getAlerts, getAlertCounts, getProperties } from "@/lib/queries";
import { PageHeader, StatCard, Card, EmptyState } from "@/components/ui";
import { SeverityBadge } from "@/components/badges";
import { timeAgo } from "@/lib/utils";

export default async function AlertsPage() {
  const [alerts, counts, properties] = await Promise.all([
    getAlerts(),
    getAlertCounts(),
    getProperties(),
  ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));

  // Critical first, then warning, then info — already sorted by recency within.
  const order = { critical: 0, warning: 1, info: 2 } as const;
  const sorted = [...alerts].sort((a, b) => order[a.severity] - order[b.severity]);

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle="Open alerts across the portfolio, grouped by severity."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Critical" value={counts.critical} tone="critical" />
        <StatCard label="Warning" value={counts.warning} tone="warning" />
        <StatCard label="Info" value={counts.info} />
        <StatCard label="Total open" value={counts.total} />
      </div>

      <Card className="mt-6">
        {sorted.length === 0 ? (
          <EmptyState message="No open alerts." />
        ) : (
          <ul className="divide-y divide-border">
            {sorted.map((a) => (
              <li key={a.id} className="flex items-start gap-3 px-4 py-3 hover:bg-surface-2">
                <SeverityBadge severity={a.severity} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{a.title}</div>
                  {a.description && (
                    <div className="text-sm text-muted">{a.description}</div>
                  )}
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted">
                    <Link
                      href={`/properties/${a.propertyId}`}
                      className="hover:text-primary"
                    >
                      {propName.get(a.propertyId) ?? "—"}
                    </Link>
                    {a.category && (
                      <span className="rounded bg-surface-2 px-1.5 py-0.5 capitalize">
                        {a.category.replace(/_/g, " ")}
                      </span>
                    )}
                  </div>
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
