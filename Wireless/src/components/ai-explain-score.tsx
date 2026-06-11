"use client";

import { useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";

/**
 * "Explain this score" — property-page companion to the health breakdown.
 * Asks /api/ai/summary?type=health for a plain-English explanation of THIS
 * property's health score (LLM when an AI key is configured, deterministic
 * fallback otherwise) and renders it inline with a source badge.
 */
type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; text: string; source: "ai" | "fallback" }
  | { status: "error" };

export function AiExplainScore({ propertyId }: { propertyId: string }) {
  const [state, setState] = useState<State>({ status: "idle" });

  async function run() {
    setState({ status: "loading" });
    try {
      const res = await fetch(`/api/ai/summary?type=health&propertyId=${propertyId}`);
      if (!res.ok) throw new Error("request failed");
      const data = (await res.json()) as { text: string; source: "ai" | "fallback" };
      setState({ status: "done", text: data.text, source: data.source });
    } catch {
      setState({ status: "error" });
    }
  }

  return (
    <div className="mt-3 border-t border-border pt-3">
      <button
        onClick={run}
        disabled={state.status === "loading"}
        className="inline-flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-1.5 text-xs font-medium text-foreground hover:bg-border disabled:opacity-50"
      >
        <Sparkles className="h-3.5 w-3.5 text-primary" />
        Explain this score
      </button>
      {state.status === "loading" && (
        <div className="mt-2 flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Generating…
        </div>
      )}
      {state.status === "error" && (
        <p className="mt-2 text-sm text-critical">Could not generate an explanation.</p>
      )}
      {state.status === "done" && (
        <div className="mt-2">
          <span
            className={
              state.source === "ai"
                ? "inline-block rounded-full bg-info-bg px-2 py-0.5 text-xs font-medium text-info"
                : "inline-block rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted"
            }
          >
            {state.source === "ai" ? "AI-generated" : "Rule-based (add AI key for LLM)"}
          </span>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{state.text}</p>
        </div>
      )}
    </div>
  );
}
