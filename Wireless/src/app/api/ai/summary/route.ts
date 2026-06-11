import { NextResponse } from "next/server";
import {
  getCompany,
  getPortfolio,
  getAlertCounts,
  getRecurringIssues,
  getAlerts,
  getProperties,
  getProjects,
  getIntegrations,
  getHealthSnapshots,
} from "@/lib/queries";
import { scoreTrend } from "@/lib/health";
import {
  summarizeAlerts,
  whatNeedsAttention,
  dailyPropertySummary,
  generateExecReport,
  summarizeVendorBlockers,
  explainHealthScore,
  type AiContext,
} from "@/lib/ai";
import { VENDOR_LABELS } from "@/components/badges";

/**
 * AI summary endpoint. GET /api/ai/summary?type=<report>[&propertyId=<id>]
 *
 * Report types (the platform's AI feature set):
 *   alerts     summarize today's network alerts          (default)
 *   attention  "what needs attention today?" action list
 *   daily      per-property daily brief
 *   exec       weekly executive report for leadership
 *   blockers   vendor blockers (projects + integration failures)
 *   health     explain one property's health score (requires propertyId)
 *
 * Returns { text, source } where source is "ai" (LLM via the Vercel AI
 * Gateway) or "fallback" (deterministic, data-derived).
 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const type = url.searchParams.get("type") ?? "alerts";
  const propertyId = url.searchParams.get("propertyId");

  // Pull everything the prompts need, in parallel.
  const [company, portfolio, alertCounts, recurring, alerts, properties, projects, integrations, snapshots] =
    await Promise.all([
      getCompany(),
      getPortfolio(),
      getAlertCounts(),
      getRecurringIssues(),
      getAlerts(),
      getProperties(),
      getProjects(),
      getIntegrations(),
      getHealthSnapshots(),
    ]);

  // Map property ids → names so alerts/projects can be labeled by site.
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  const now = new Date();

  // Shape the full context object the AI module consumes.
  const ctx: AiContext = {
    company: company.name,
    properties: portfolio.map((p) => {
      // Before/after: week-over-week movement from the snapshot history.
      const trend = scoreTrend(
        snapshots.filter((s) => s.propertyId === p.property.id),
        p.health.score,
        now
      );
      return {
        name: p.property.name,
        vendor: p.property.managedBy,
        score: p.health.score,
        band: p.health.band,
        openAlerts: p.openAlerts,
        criticalAlerts: p.criticalAlerts,
        offlineAps: p.apOffline,
        deductions: p.health.deductions,
        weekAgoScore: trend.weekAgo,
        delta: trend.delta,
      };
    }),
    alertCounts,
    recurring,
    criticalAlerts: alerts
      .filter((a) => a.severity === "critical" && a.status !== "resolved")
      .map((a) => ({
        property: propName.get(a.propertyId) ?? "—",
        title: a.title,
        description: a.description,
        category: a.category,
      })),
    blockers: {
      projects: projects.map((p) => ({
        name: p.name,
        property: p.propertyId ? (propName.get(p.propertyId) ?? null) : null,
        status: p.status,
        dueDate: p.dueDate ? p.dueDate.toISOString().slice(0, 10) : null,
        overdue: Boolean(p.dueDate && p.status !== "completed" && p.dueDate < now),
      })),
      integrationErrors: integrations
        .filter((i) => i.status === "error" && i.lastError)
        .map((i) => ({ vendor: VENDOR_LABELS[i.vendor] ?? i.vendor, error: i.lastError! })),
    },
  };

  // Dispatch to the requested generator.
  switch (type) {
    case "attention":
      return NextResponse.json(await whatNeedsAttention(ctx));
    case "daily":
      return NextResponse.json(await dailyPropertySummary(ctx));
    case "exec":
      return NextResponse.json(await generateExecReport(ctx));
    case "blockers":
      return NextResponse.json(await summarizeVendorBlockers(ctx));
    case "health": {
      const name = propertyId ? propName.get(propertyId) : undefined;
      if (!name) {
        return NextResponse.json(
          { error: "health requires a valid propertyId" },
          { status: 400 }
        );
      }
      return NextResponse.json(await explainHealthScore(ctx, name));
    }
    case "alerts":
      return NextResponse.json(await summarizeAlerts(ctx));
    default:
      return NextResponse.json({ error: `unknown type "${type}"` }, { status: 400 });
  }
}
