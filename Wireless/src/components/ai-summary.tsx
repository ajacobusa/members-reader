"use client";

import { useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { Card } from "@/components/ui";

/**
 * AI assistant panel (client component).
 *
 * Two on-demand actions — summarize today's alerts, and draft an executive
 * report — backed by /api/ai/summary. Shows a loading state and a small badge
 * noting whether the text came from the LLM ("AI") or the deterministic
 * fallback, so the output is always transparent about its source.
 */
type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; text: string; source: "ai" | "fallback" }
  | { status: "error" };

export function AiSummaryPanel() {
  // Track the request lifecycle for the panel.
  const [state, setState] = useState<State>({ status: "idle" });

  // Call the API for the given report type and store the result.
  async function run(type: string) {
    setState({ status: "loading" });
    try {
      const res = await fetch(`/api/ai/summary?type=${type}`);
      if (!res.ok) throw new Error("request failed");
      const data = (await res.json()) as { text: string; source: "ai" | "fallback" };
      setState({ status: "done", text: data.text, source: data.source });
    } catch {
      setState({ status: "error" });
    }
  }

  // The report set: secondary buttons for ops views, primary for the exec report.
  const REPORTS: { type: string; label: string; primary?: boolean }[] = [
    { type: "attention", label: "What needs attention?" },
    { type: "alerts", label: "Summarize alerts" },
    { type: "daily", label: "Daily summary" },
    { type: "blockers", label: "Vendor blockers" },
    { type: "exec", label: "Weekly exec report", primary: true },
  ];

  return (
    <Card className="p-4">
      {/* Header row: title + one trigger button per report type. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-primary" />
          AI assistant
        </div>
        <div className="flex flex-wrap gap-2">
          {REPORTS.map((r) => (
            <button
              key={r.type}
              onClick={() => run(r.type)}
              disabled={state.status === "loading"}
              className={
                r.primary
                  ? "rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-fg hover:opacity-90 disabled:opacity-50"
                  : "rounded-lg bg-surface-2 px-3 py-1.5 text-xs font-medium text-foreground hover:bg-border disabled:opacity-50"
              }
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Result area: prompt, spinner, error, or the generated text. */}
      <div className="mt-3 text-sm">
        {state.status === "idle" && (
          <p className="text-muted">
            Generate a plain-English summary of today&apos;s alerts, or an executive
            update for leadership.
          </p>
        )}
        {state.status === "loading" && (
          <div className="flex items-center gap-2 text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Generating…
          </div>
        )}
        {state.status === "error" && (
          <p className="text-critical">Could not generate a summary. Try again.</p>
        )}
        {state.status === "done" && (
          <div>
            {/* Transparency badge: LLM output vs deterministic fallback. */}
            <span
              className={
                state.source === "ai"
                  ? "inline-block rounded-full bg-info-bg px-2 py-0.5 text-xs font-medium text-info"
                  : "inline-block rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted"
              }
            >
              {state.source === "ai" ? "AI-generated" : "Rule-based (add AI key for LLM)"}
            </span>
            {/* Preserve newlines from the generated text. */}
            <p className="mt-2 whitespace-pre-wrap leading-relaxed">{state.text}</p>
          </div>
        )}
      </div>
    </Card>
  );
}
