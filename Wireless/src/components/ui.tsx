// `cn` joins CSS class names, letting callers add extra classes on top of defaults.
import { cn } from "@/lib/utils";
// `ReactNode` is the type for anything React can render (text, elements, lists, etc.).
import type { ReactNode } from "react";

// Reusable page heading: a title, an optional subtitle, and optional action buttons.
// The `?` on subtitle and actions marks them as optional props.
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    // Row with the title block on the left and the action buttons pushed to the right.
    <div className="mb-6 flex items-start justify-between gap-4">
      {/* Left side: the main title and (if provided) a subtitle underneath. */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {/* Only render the subtitle paragraph when a subtitle was passed in. */}
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {/* Right side: any action elements (e.g. buttons) the caller provided. */}
      {actions}
    </div>
  );
}

// A simple rounded container with a border and shadow used to group content.
// `children` is whatever is placed inside the card; `className` adds extra styles.
export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    // Merge the default card look with any extra classes the caller passes.
    <div
      className={cn(
        "rounded-xl border border-border bg-surface shadow-sm",
        className
      )}
    >
      {/* Render whatever was placed inside the card. */}
      {children}
    </div>
  );
}

// A small "statistic" card: a label, a big value, and an optional hint line.
// `tone` colors the value (e.g. red for critical); it defaults to "default".
export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "critical" | "warning" | "good";
}) {
  // Pick the text color for the value based on the tone (chained ternary).
  const valueTone =
    tone === "critical"
      ? "text-critical"
      : tone === "warning"
        ? "text-warning"
        : tone === "good"
          ? "text-good"
          : "text-foreground";
  return (
    // Reuse the Card component for the container and add inner padding.
    <Card className="p-4">
      {/* Small uppercase label describing what the number means. */}
      <div className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </div>
      {/* The main value, shown large; its color comes from `valueTone`. */}
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums", valueTone)}>
        {value}
      </div>
      {/* Optional small hint text, only shown when a hint was provided. */}
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

/** Minimal table primitives sharing one style. */
// Wraps a real HTML <table> so it can scroll sideways on narrow screens.
export function Table({ children }: { children: ReactNode }) {
  return (
    // `overflow-x-auto` adds a horizontal scrollbar only when the table is too wide.
    <div className="overflow-x-auto">
      {/* The actual table; `children` are the rows/headers placed inside. */}
      <table className="w-full text-sm">{children}</table>
    </div>
  );
}

// A styled table header cell (<th>). `className` lets callers tweak individual cells.
export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    // Merge the default header styling with any extra classes passed in.
    <th
      className={cn(
        "border-b border-border px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted",
        className
      )}
    >
      {children}
    </th>
  );
}

// A styled table data cell (<td>) sharing the same look as the header.
export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    // Default cell styling plus any extra classes the caller adds.
    <td className={cn("border-b border-border px-4 py-3 align-middle", className)}>
      {children}
    </td>
  );
}

// A centered message shown when a list or table has no data to display.
export function EmptyState({ message }: { message: string }) {
  return (
    <div className="px-4 py-10 text-center text-sm text-muted">{message}</div>
  );
}
