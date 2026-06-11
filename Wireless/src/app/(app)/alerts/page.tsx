// Client-side navigation for property links.
import Link from "next/link";
// Data reads (work identically in mock and Postgres modes).
import { getAlerts, getAlertCounts, getProperties } from "@/lib/queries";
// The alert-intelligence engine: playbook guidance, recurrence, grouping, timeline.
import {
  enrichAlert,
  groupAlerts,
  buildTimeline,
  type AlertInsight,
} from "@/lib/alert-intel";
// Shared layout + badge components.
import { PageHeader, StatCard, Card, EmptyState } from "@/components/ui";
import { SeverityBadge, VENDOR_LABELS } from "@/components/badges";
import { timeAgo } from "@/lib/utils";
// Server action: one-click incident creation from an alert (ticketing flow).
import { createIncidentFromAlert } from "@/app/actions/incidents";
// Writes need a database; in mock mode the button is hidden.
import { hasDatabase } from "@/db/client";
import type { Alert, IntegrationVendorName } from "@/db/schema";

// Alert intelligence page: open alerts with root cause + recommended action,
// portfolio groupings (property / category / vendor), and a history timeline.
export default async function AlertsPage() {
  // Pull everything in parallel; `alerts` includes resolved rows for history.
  const [alerts, counts, properties] = await Promise.all([
    getAlerts(),
    getAlertCounts(),
    getProperties(),
  ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  const propVendor = new Map(properties.map((p) => [p.id, p.managedBy]));

  // Enrich every alert once; reuse for all views below.
  const enriched = alerts.map((a) => ({ alert: a, insight: enrichAlert(a, alerts) }));
  const open = enriched.filter((e) => e.alert.status !== "resolved");
  // Effective-severity ordering: escalated alerts surface with their bumped rank.
  const order = { critical: 0, warning: 1, info: 2 } as const;
  open.sort(
    (a, b) =>
      order[a.insight.effectiveSeverity] - order[b.insight.effectiveSeverity] ||
      b.alert.raisedAt.getTime() - a.alert.raisedAt.getTime()
  );

  // Portfolio groupings (open alerts only — history lives in the timeline).
  const openAlerts = open.map((e) => e.alert);
  const byProperty = groupAlerts(openAlerts, (a) => propName.get(a.propertyId) ?? "—");
  const byCategory = groupAlerts(openAlerts, (a) =>
    (a.category ?? "uncategorized").replace(/_/g, " ")
  );
  const byVendor = groupAlerts(openAlerts, (a) => {
    const v = propVendor.get(a.propertyId);
    return v ? VENDOR_LABELS[v as IntegrationVendorName] : (a.source ?? "unknown");
  });

  // Chronological event stream (raised + resolved), newest first.
  const timeline = buildTimeline(alerts).slice(0, 30);

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle="Open alerts with root cause and recommended action; grouped views and full history below."
      />

      {/* Severity stat cards (counts use stored severity, matching the dashboard). */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Critical" value={counts.critical} tone="critical" />
        <StatCard label="Warning" value={counts.warning} tone="warning" />
        <StatCard label="Info" value={counts.info} />
        <StatCard label="Total open" value={counts.total} />
      </div>

      {/* Open alerts, each with playbook intelligence. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Open alerts ({open.length})
        </div>
        {open.length === 0 ? (
          <EmptyState message="No open alerts." />
        ) : (
          <ul className="divide-y divide-border">
            {open.map(({ alert, insight }) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                insight={insight}
                propertyName={propName.get(alert.propertyId) ?? "—"}
              />
            ))}
          </ul>
        )}
      </Card>

      {/* Grouped rollups: where the pain concentrates. */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <GroupCard title="By property" groups={byProperty} />
        <GroupCard title="By category" groups={byCategory} />
        <GroupCard title="By vendor" groups={byVendor} />
      </div>

      {/* History timeline: raised/resolved events, newest first. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          History timeline
        </div>
        {timeline.length === 0 ? (
          <EmptyState message="No alert history yet." />
        ) : (
          <ul className="divide-y divide-border">
            {timeline.map((ev, i) => (
              <li key={`${ev.alert.id}-${ev.kind}-${i}`} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                {/* Event marker: red dot = raised, green dot = resolved. */}
                <span
                  className={
                    ev.kind === "raised"
                      ? "h-2 w-2 shrink-0 rounded-full bg-critical"
                      : "h-2 w-2 shrink-0 rounded-full bg-good"
                  }
                />
                <span className="w-16 shrink-0 text-xs uppercase tracking-wide text-muted">
                  {ev.kind}
                </span>
                <span className="min-w-0 flex-1 truncate">{ev.alert.title}</span>
                <span className="hidden shrink-0 text-xs text-muted sm:inline">
                  {propName.get(ev.alert.propertyId) ?? "—"}
                </span>
                <span className="shrink-0 text-xs text-muted">{timeAgo(ev.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

// One open alert with its intelligence: severity, chips, cause, and action.
function AlertRow({
  alert,
  insight,
  propertyName,
}: {
  alert: Alert;
  insight: AlertInsight;
  propertyName: string;
}) {
  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-3">
        <SeverityBadge severity={insight.effectiveSeverity} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{alert.title}</span>
            {/* Recurrence/escalation chips explain why severity may differ from stored. */}
            {insight.recurring && (
              <span className="rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning">
                recurring ×{insight.occurrences}
              </span>
            )}
            {insight.escalated && (
              <span className="rounded-full bg-critical-bg px-2 py-0.5 text-xs font-medium text-critical">
                escalated from {alert.severity}
              </span>
            )}
          </div>
          {alert.description && (
            <div className="mt-0.5 text-sm text-muted">{alert.description}</div>
          )}
          {/* The playbook: cause + action in the runbook format. */}
          <div className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-sm">
            <div>
              <span className="font-medium">Possible cause:</span>{" "}
              <span className="text-muted">{insight.rootCause}</span>
            </div>
            <div className="mt-1">
              <span className="font-medium">Action:</span>{" "}
              <span className="text-muted">{insight.recommendedAction}</span>
            </div>
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs text-muted">
            <Link href={`/properties/${alert.propertyId}`} className="hover:text-primary">
              {propertyName}
            </Link>
            {alert.category && (
              <span className="rounded bg-surface-2 px-1.5 py-0.5 capitalize">
                {alert.category.replace(/_/g, " ")}
              </span>
            )}
            <span>{timeAgo(alert.raisedAt)}</span>
            {/* Ticketing: turn this alert into a tracked incident (DB mode only). */}
            {hasDatabase() && (
              <form action={createIncidentFromAlert} className="ml-auto">
                <input type="hidden" name="alertId" value={alert.id} />
                <button className="rounded-lg bg-surface-2 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-border">
                  Create incident
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

// Compact rollup table for one grouping dimension.
function GroupCard({
  title,
  groups,
}: {
  title: string;
  groups: { key: string; total: number; critical: number; warning: number }[];
}) {
  return (
    <Card className="p-4">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-3 space-y-2">
        {groups.length === 0 && <div className="text-sm text-muted">No open alerts.</div>}
        {groups.slice(0, 6).map((g) => (
          <div key={g.key} className="flex items-center justify-between text-sm">
            <span className="min-w-0 truncate capitalize text-muted">{g.key}</span>
            <span className="ml-2 shrink-0 tabular-nums">
              {g.critical > 0 && <span className="font-medium text-critical">{g.critical}c </span>}
              {g.warning > 0 && <span className="font-medium text-warning">{g.warning}w </span>}
              <span className="text-muted">{g.total}</span>
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
