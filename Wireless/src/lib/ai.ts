import "server-only";
import { generateText } from "ai";
import { playbookFor } from "./alert-intel";

/**
 * AI layer — natural-language summaries and executive reports.
 *
 * Five generators (the platform's AI feature set):
 *   summarizeAlerts        "Summarize today's network alerts"
 *   whatNeedsAttention     "What needs attention today?"
 *   dailyPropertySummary   per-property daily brief for the whole portfolio
 *   generateExecReport     weekly executive update for leadership
 *   summarizeVendorBlockers "Summarize vendor blockers"
 *   explainHealthScore     "Explain this property's health score"
 *
 * Two modes, chosen automatically (same optional-by-default pattern as
 * auth/DB): with an AI Gateway credential, a Claude model writes the
 * narrative; without one, a deterministic fallback builds a solid summary
 * straight from the data. Fallbacks lean on the alert-intelligence playbook
 * so even rule-based output includes recommended actions. Never throws.
 *
 * Model is configurable via AI_MODEL. Verify current gateway ids with:
 *   curl -s https://ai-gateway.vercel.sh/v1/models
 */

const AI_MODEL = process.env.AI_MODEL ?? "anthropic/claude-sonnet-4.5";

/** True when an AI Gateway credential is configured (API key or Vercel OIDC). */
export function aiEnabled(): boolean {
  return Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN);
}

// ---------------------------------------------------------------------------
// Input shapes — assembled by the API route from the data layer.
// ---------------------------------------------------------------------------

export interface AiPropertyLine {
  name: string;
  vendor: string | null;
  score: number;
  band: string;
  openAlerts: number;
  criticalAlerts: number;
  offlineAps: number;
  /** Itemized health deductions (reason / count / points) for explainability. */
  deductions: { reason: string; count: number; points: number }[];
  /** The score ~7 days ago and the change since (null without history). */
  weekAgoScore: number | null;
  delta: number | null;
}

export interface AiCriticalAlert {
  property: string;
  title: string;
  description?: string | null;
  category?: string | null;
}

export interface AiBlockerContext {
  projects: {
    name: string;
    property: string | null;
    status: string;
    dueDate: string | null;
    overdue: boolean;
  }[];
  integrationErrors: { vendor: string; error: string }[];
}

export interface AiContext {
  company: string;
  properties: AiPropertyLine[]; // worst-first
  alertCounts: { critical: number; warning: number; info: number; total: number };
  recurring: { category: string; count: number }[];
  criticalAlerts: AiCriticalAlert[];
  blockers: AiBlockerContext;
}

export interface AiResult {
  text: string;
  /** Where the text came from, so the UI can be transparent about it. */
  source: "ai" | "fallback";
}

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

export async function summarizeAlerts(ctx: AiContext): Promise<AiResult> {
  const system =
    "You are a network operations analyst for a hotel group. Write a tight, " +
    "skimmable summary of today's WiFi/IoT alerts for an on-call engineer. " +
    "Lead with what needs action now. Use short paragraphs or bullets. No fluff.";
  return run(system, portfolioPrompt(ctx) + "\nWrite the alert summary.", () =>
    fallbackAlertSummary(ctx)
  );
}

export async function whatNeedsAttention(ctx: AiContext): Promise<AiResult> {
  const system =
    "You are the network operations lead running the morning standup for a " +
    "hotel group. Produce a ranked TODAY action list: most urgent first, one " +
    "line each — what, where, and the first concrete step. Max 6 items.";
  return run(system, portfolioPrompt(ctx) + "\nWrite today's action list.", () =>
    fallbackAttention(ctx)
  );
}

export async function dailyPropertySummary(ctx: AiContext): Promise<AiResult> {
  const system =
    "You are a network operations analyst. Write a daily per-property brief " +
    "for a hotel portfolio: one line per property — health, what changed, top " +
    "issue. Plain English, ordered worst to best.";
  return run(system, portfolioPrompt(ctx) + "\nWrite the daily property summary.", () =>
    fallbackDaily(ctx)
  );
}

export async function generateExecReport(ctx: AiContext): Promise<AiResult> {
  const system =
    "You are a network operations lead writing the weekly executive update " +
    "for hotel leadership. Audience is non-technical. Cover overall health, " +
    "the few things that matter, business impact (guest experience), and this " +
    "week's focus. ~150 words, confident, plain English.";
  return run(system, portfolioPrompt(ctx) + "\nWrite the weekly executive update.", () =>
    fallbackExecReport(ctx)
  );
}

export async function summarizeVendorBlockers(ctx: AiContext): Promise<AiResult> {
  const b = ctx.blockers;
  const system =
    "You are a vendor/project manager for a hotel group's network operations. " +
    "Summarize current vendor blockers: blocked or overdue projects and broken " +
    "vendor integrations. For each, say who is blocked, why it matters, and " +
    "the next escalation step. Short bullets.";
  const prompt =
    `Company: ${ctx.company}\n` +
    `Projects:\n${
      b.projects
        .map(
          (p) =>
            `- ${p.name} [${p.status}${p.overdue ? ", OVERDUE" : ""}] ` +
            `(${p.property ?? "portfolio-wide"}, due ${p.dueDate ?? "n/a"})`
        )
        .join("\n") || "- none"
    }\n` +
    `Integration errors:\n${
      b.integrationErrors.map((e) => `- ${e.vendor}: ${e.error}`).join("\n") || "- none"
    }\n\nWrite the vendor blocker summary.`;
  return run(system, prompt, () => fallbackBlockers(ctx));
}

export async function explainHealthScore(
  ctx: AiContext,
  propertyName: string
): Promise<AiResult> {
  const p = ctx.properties.find((x) => x.name === propertyName);
  if (!p) return { text: `No property named "${propertyName}" found.`, source: "fallback" };
  const system =
    "You are a network operations analyst. Explain a hotel property's 0-100 " +
    "WiFi health score to a property manager: why it is what it is (each " +
    "deduction in plain English) and the single change that would recover the " +
    "most points. 3-5 sentences.";
  const prompt =
    `Property: ${p.name} (vendor: ${p.vendor ?? "n/a"})\n` +
    `Score: ${p.score}/100 (${p.band}). Formula: 100 minus itemized deductions.\n` +
    `Deductions:\n${
      p.deductions.map((d) => `- ${d.reason} ×${d.count} = −${d.points}`).join("\n") ||
      "- none"
    }\n\nExplain the score.`;
  return run(system, prompt, () => fallbackExplainScore(p));
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/** Shared portfolio context block used by the portfolio-level prompts. */
function portfolioPrompt(ctx: AiContext): string {
  return (
    `Company: ${ctx.company}\n` +
    `Open alerts — critical: ${ctx.alertCounts.critical}, warning: ${ctx.alertCounts.warning}, info: ${ctx.alertCounts.info}.\n` +
    `Recurring issue categories: ${ctx.recurring.map((r) => `${r.category} (${r.count})`).join(", ") || "none"}.\n` +
    `Critical alerts:\n${
      ctx.criticalAlerts
        .map((a) => `- ${a.property}: ${a.title}${a.description ? ` — ${a.description}` : ""}`)
        .join("\n") || "- none"
    }\n` +
    `Property health (worst first):\n${ctx.properties
      .map(
        (p) =>
          `- ${p.name} [${p.vendor ?? "n/a"}] score ${p.score} (${p.band}), ` +
          `${p.openAlerts} open (${p.criticalAlerts} crit), ${p.offlineAps} APs offline` +
          // The before/after signal: week-over-week movement when history exists.
          (p.delta !== null ? `, 7d change ${p.delta >= 0 ? "+" : ""}${p.delta} (was ${p.weekAgoScore})` : "")
      )
      .join("\n")}\n`
  );
}

/**
 * Call the model when enabled; otherwise (or on any error) use the
 * deterministic fallback. Never throws — the UI always gets usable text.
 */
async function run(
  system: string,
  prompt: string,
  fallback: () => string
): Promise<AiResult> {
  if (!aiEnabled()) return { text: fallback(), source: "fallback" };
  try {
    const { text } = await generateText({ model: AI_MODEL, system, prompt });
    return { text: text.trim(), source: "ai" };
  } catch {
    // Bad key, network, or model error → degrade gracefully rather than fail.
    return { text: fallback(), source: "fallback" };
  }
}

function avgScore(props: AiPropertyLine[]): number {
  if (props.length === 0) return 100;
  return Math.round(props.reduce((n, p) => n + p.score, 0) / props.length);
}

// ---- Deterministic fallbacks ----------------------------------------------

function fallbackAlertSummary(ctx: AiContext): string {
  const lines: string[] = [];
  lines.push(
    `${ctx.alertCounts.total} open alerts across ${ctx.properties.length} properties: ` +
      `${ctx.alertCounts.critical} critical, ${ctx.alertCounts.warning} warning, ${ctx.alertCounts.info} info.`
  );
  if (ctx.criticalAlerts.length > 0) {
    lines.push("\nNeeds action now:");
    for (const a of ctx.criticalAlerts) lines.push(`• ${a.property}: ${a.title}`);
  }
  const worst = ctx.properties[0];
  if (worst) {
    lines.push(
      `\nMost affected site: ${worst.name} (health ${worst.score}, ${worst.offlineAps} APs offline).`
    );
  }
  if (ctx.recurring.length > 0) {
    const top = ctx.recurring[0];
    lines.push(
      `Top recurring issue: ${top.category.replace(/_/g, " ")} (${top.count} occurrences).`
    );
  }
  return lines.join("\n");
}

function fallbackAttention(ctx: AiContext): string {
  const items: string[] = [];
  // Criticals first, each with the playbook's first concrete step.
  for (const a of ctx.criticalAlerts.slice(0, 4)) {
    const action = playbookFor(a.category ?? null).action.split(",")[0];
    items.push(`${items.length + 1}. ${a.property}: ${a.title} → ${action}.`);
  }
  // Then the worst property if it isn't already covered.
  const worst = ctx.properties[0];
  if (worst && worst.score < 60) {
    items.push(
      `${items.length + 1}. Review ${worst.name} (health ${worst.score}) — ` +
        `${worst.openAlerts} open alerts, ${worst.offlineAps} APs offline.`
    );
  }
  if (items.length === 0) return "Nothing urgent today — all properties are healthy.";
  return `Today's priorities:\n${items.join("\n")}`;
}

function fallbackDaily(ctx: AiContext): string {
  const lines = ctx.properties.map((p) => {
    const top = p.deductions[0];
    const issue = top ? ` — top issue: ${top.reason.toLowerCase()} (−${top.points})` : "";
    // Call out meaningful week-over-week movement (±5 or more).
    const move =
      p.delta !== null && Math.abs(p.delta) >= 5
        ? ` (${p.delta > 0 ? "▲ up" : "▼ down"} ${Math.abs(p.delta)} from ${p.weekAgoScore} last week)`
        : "";
    return `• ${p.name}: ${p.score}/100 (${p.band})${move}, ${p.openAlerts} open alerts${
      p.criticalAlerts ? ` (${p.criticalAlerts} critical)` : ""
    }${issue}`;
  });
  return `Daily property summary — ${ctx.company}:\n${lines.join("\n")}`;
}

function fallbackExecReport(ctx: AiContext): string {
  const avg = avgScore(ctx.properties);
  const below = ctx.properties.filter((p) => p.score < 60);
  const lines: string[] = [];
  lines.push(
    `Portfolio health is averaging ${avg}/100 across ${ctx.properties.length} properties.`
  );
  if (below.length > 0) {
    lines.push(
      `${below.length} site(s) need attention: ${below.map((p) => `${p.name} (${p.score})`).join(", ")}.`
    );
  } else {
    lines.push("All sites are in good shape this week.");
  }
  lines.push(
    `There are ${ctx.alertCounts.critical} critical and ${ctx.alertCounts.warning} warning alerts open. ` +
      `Critical issues affect guest WiFi and connectivity at the lowest-scoring sites.`
  );
  const themes = ctx.recurring.slice(0, 3).map((r) => r.category.replace(/_/g, " "));
  if (themes.length > 0) lines.push(`Recurring themes to watch: ${themes.join(", ")}.`);
  lines.push(
    `This week's focus: resolve the critical alerts above and progress the fleet firmware upgrade.`
  );
  return lines.join(" ");
}

function fallbackBlockers(ctx: AiContext): string {
  const { projects, integrationErrors } = ctx.blockers;
  const blocked = projects.filter((p) => p.status === "blocked" || p.overdue);
  const lines: string[] = [];
  if (blocked.length === 0 && integrationErrors.length === 0) {
    return "No vendor blockers: no blocked or overdue projects, all integrations healthy.";
  }
  if (blocked.length > 0) {
    lines.push("Blocked / overdue projects:");
    for (const p of blocked) {
      lines.push(
        `• ${p.name} (${p.property ?? "portfolio-wide"}) — ${p.status}` +
          `${p.overdue ? `, overdue since ${p.dueDate}` : ""}. Escalate with the owning vendor.`
      );
    }
  }
  if (integrationErrors.length > 0) {
    lines.push("\nIntegration failures:");
    for (const e of integrationErrors) {
      lines.push(`• ${e.vendor}: ${e.error} — re-check credentials and re-run sync.`);
    }
  }
  return lines.join("\n");
}

function fallbackExplainScore(p: AiPropertyLine): string {
  if (p.deductions.length === 0) {
    return `${p.name} scores ${p.score}/100 — no deductions; the property is fully healthy.`;
  }
  const total = p.deductions.reduce((n, d) => n + d.points, 0);
  const biggest = [...p.deductions].sort((a, b) => b.points - a.points)[0];
  const parts = p.deductions.map((d) => `${d.reason.toLowerCase()} ×${d.count} (−${d.points})`);
  // The before/after framing, when this property has been sliding.
  const dropped =
    p.delta !== null && p.delta <= -5
      ? `${p.name} dropped from ${p.weekAgoScore} to ${p.score} over the past week. `
      : "";
  return (
    `${dropped}${p.name} scores ${p.score}/100 (${p.band}) — ${total} points in deductions: ` +
    `${parts.join(", ")}. ` +
    `Largest single impact: ${biggest.reason.toLowerCase()} (−${biggest.points}); ` +
    `fixing that alone would lift the score to ${Math.min(100, p.score + biggest.points)}.`
  );
}
