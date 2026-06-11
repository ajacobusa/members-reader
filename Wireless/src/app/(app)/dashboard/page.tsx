// Next.js' built-in component for client-side navigation between pages (faster than a plain <a> tag).
import Link from "next/link";
// Import the data-fetching helper functions from our shared queries module.
import {
  // Returns one row per property with its rolled-up health and counts.
  getPortfolio,
  // Returns how many alerts exist at each severity level (critical/warning/info).
  getAlertCounts,
  // Returns the most common recurring problem categories across the portfolio.
  getRecurringIssues,
} from "@/lib/queries";
// Reusable presentational UI building blocks (header, stat cards, table parts).
import { PageHeader, StatCard, Card, Table, Th, Td } from "@/components/ui";
// Small colored badge components for showing a health number and an alert severity.
import { HealthScore, SeverityBadge } from "@/components/badges";
// Client-side AI panel: on-demand alert summaries and executive reports.
import { AiSummaryPanel } from "@/components/ai-summary";

// The default export is the page itself. It is `async` because it awaits data
// before rendering — this is a React Server Component that runs on the server.
export default async function DashboardPage() {
  // Fire all three data queries at the same time (in parallel) and wait for all
  // to finish. Destructuring assigns each resolved result to its own variable.
  const [portfolio, alertCounts, recurring] = await Promise.all([
    getPortfolio(),
    getAlertCounts(),
    getRecurringIssues(),
  ]);

  // Sum every property's access-point count to get the portfolio-wide total.
  const totalAps = portfolio.reduce((n, p) => n + p.apCount, 0);
  // Sum every property's offline access points to get the total currently down.
  const offlineAps = portfolio.reduce((n, p) => n + p.apOffline, 0);
  // Average health across all properties, rounded to a whole number.
  const avgHealth = Math.round(
    // Add up every property's health score, then divide by the number of
    // properties. The `|| 1` guards against dividing by zero when the list is empty.
    portfolio.reduce((n, p) => n + p.health.score, 0) / (portfolio.length || 1)
  );

  // Everything below is the JSX (the visual markup) this page renders.
  // The React fragment (<>...</>) lets us return multiple sibling elements without a wrapper div.
  return (
    <>
      {/* The page title and subtitle shown at the top of the screen. */}
      <PageHeader
        title="Portfolio Dashboard"
        subtitle="Health and alerts across every property. Worst-performing sites surface first."
      />

      {/* A responsive grid of summary "stat" cards: 2 columns on small screens, 4 on large. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* How many properties exist — just the array length. */}
        <StatCard label="Properties" value={portfolio.length} />
        {/* Average health, color-coded: green when >=85, amber when >=60, red below that. */}
        <StatCard
          label="Avg health"
          value={avgHealth}
          tone={avgHealth >= 85 ? "good" : avgHealth >= 60 ? "warning" : "critical"}
        />
        {/* Offline-vs-total access points; amber tone if any are offline. */}
        <StatCard
          label="APs offline"
          value={`${offlineAps} / ${totalAps}`}
          tone={offlineAps > 0 ? "warning" : "good"}
        />
        {/* Count of critical alerts; red tone if there are any. */}
        <StatCard
          label="Critical alerts"
          value={alertCounts.critical}
          tone={alertCounts.critical > 0 ? "critical" : "good"}
        />
      </div>

      {/* AI assistant: generate an alert summary or executive report on demand. */}
      <div className="mt-6">
        <AiSummaryPanel />
      </div>

      {/* Main content grid below the stat cards: one wide table + a narrow sidebar column. */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* The property-health table spans 2 of the 3 grid columns on large screens. */}
        <Card className="lg:col-span-2">
          {/* Card heading bar. */}
          <div className="border-b border-border px-4 py-3 text-sm font-semibold">
            Property health
          </div>
          <Table>
            {/* Table header row defining the five columns. */}
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
              {/* Loop over each property, pulling out the fields we need via destructuring,
                  and render one table row per property. */}
              {portfolio.map(({ property, health, apCount, apOffline, openAlerts, criticalAlerts }) => (
                // `key` gives React a stable identity for each row so it can update efficiently.
                <tr key={property.id} className="hover:bg-surface-2">
                  {/* Property name, linked to that property's detail page. */}
                  <Td>
                    <Link
                      href={`/properties/${property.id}`}
                      className="font-medium text-foreground hover:text-primary"
                    >
                      {property.name}
                    </Link>
                  </Td>
                  {/* City and region of the property. */}
                  <Td className="text-muted">
                    {property.city}, {property.region}
                  </Td>
                  {/* Online APs over total APs (e.g. "8/10"). `tabular-nums` keeps digits aligned. */}
                  <Td className="text-right tabular-nums">
                    {apCount - apOffline}/{apCount}
                  </Td>
                  {/* Number of open alerts; append a red "(N crit)" note only if there are criticals. */}
                  <Td className="text-right tabular-nums">
                    {openAlerts}
                    {criticalAlerts > 0 && (
                      <span className="ml-1 text-critical">({criticalAlerts} crit)</span>
                    )}
                  </Td>
                  {/* Compact health-score badge for this property. */}
                  <Td className="text-right">
                    <HealthScore score={health.score} band={health.band} size="sm" />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        {/* The narrow right-hand sidebar column holding two stacked cards. */}
        <div className="space-y-6">
          {/* Card 1: a breakdown of alert counts per severity. */}
          <Card className="p-4">
            <div className="text-sm font-semibold">Alerts by severity</div>
            <div className="mt-3 space-y-2">
              {/* One row per severity level; SeverityRow is the small helper defined below. */}
              <SeverityRow label="Critical" count={alertCounts.critical} severity="critical" />
              <SeverityRow label="Warning" count={alertCounts.warning} severity="warning" />
              <SeverityRow label="Info" count={alertCounts.info} severity="info" />
            </div>
            {/* Link to the full alerts page. */}
            <Link
              href="/alerts"
              className="mt-4 inline-block text-sm font-medium text-primary hover:underline"
            >
              View all alerts →
            </Link>
          </Card>

          {/* Card 2: the top recurring problem categories. */}
          <Card className="p-4">
            <div className="text-sm font-semibold">Recurring issues</div>
            <div className="mt-3 space-y-2">
              {/* Show only the first 5 recurring issues, rendering a label/count row for each. */}
              {recurring.slice(0, 5).map((r) => (
                <div key={r.category} className="flex items-center justify-between text-sm">
                  {/* Turn a snake_case category like "weak_signal" into "weak signal". */}
                  <span className="capitalize text-muted">
                    {r.category.replace(/_/g, " ")}
                  </span>
                  {/* How many times this category occurred. */}
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

// A small private helper component that renders a single "severity badge + label + count" row.
// It is only used inside this file, so it lives at the bottom rather than in a shared module.
function SeverityRow({
  // The text label to show (e.g. "Critical").
  label,
  // The numeric count to display on the right.
  count,
  // Which severity this row represents — restricted to these three exact strings.
  severity,
}: {
  label: string;
  count: number;
  severity: "critical" | "warning" | "info";
}) {
  return (
    // Lay the badge/label on the left and the count on the right, vertically centered.
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm">
        {/* Colored dot/pill indicating the severity. */}
        <SeverityBadge severity={severity} />
        <span className="text-muted">{label}</span>
      </div>
      {/* The count, shown larger and bold. */}
      <span className="text-lg font-semibold tabular-nums">{count}</span>
    </div>
  );
}
