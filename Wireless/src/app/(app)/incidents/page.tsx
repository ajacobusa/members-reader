// Client-side navigation for property links.
import Link from "next/link";
// Data reads (mock or Postgres, chosen automatically).
import { getIncidents, getIncidentNotes, getProperties } from "@/lib/queries";
// Whether ticketing writes are possible (they need a database).
import { hasDatabase } from "@/db/client";
// SLA helpers shared with the automation rules.
import { slaState, formatSla } from "@/lib/incidents";
// Server actions powering the forms below.
import { updateIncident, addIncidentNote } from "@/app/actions/incidents";
// Shared layout + badge components.
import { PageHeader, StatCard, Card, EmptyState } from "@/components/ui";
import { SeverityBadge } from "@/components/badges";
import { cn, timeAgo } from "@/lib/utils";
import { incidentStatus, type Incident } from "@/db/schema";

// Visual style per workflow status.
const STATUS_STYLE: Record<Incident["status"], string> = {
  open: "bg-critical-bg text-critical ring-critical/20",
  investigating: "bg-warning-bg text-warning ring-warning/20",
  vendor_escalated: "bg-info-bg text-info ring-info/20",
  resolved: "bg-good-bg text-good ring-good/20",
};

// Incident ticketing page: workflow status, owners, SLA timers, and notes.
export default async function IncidentsPage() {
  const [incidents, notes, properties] = await Promise.all([
    getIncidents(),
    getIncidentNotes(),
    getProperties(),
  ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  // Group the work-log notes by incident for fast lookup while rendering.
  const notesByIncident = new Map<string, typeof notes>();
  for (const note of notes) {
    notesByIncident.set(note.incidentId, [
      ...(notesByIncident.get(note.incidentId) ?? []),
      note,
    ]);
  }

  const now = new Date();
  // Active incidents first (worst status first), resolved at the bottom.
  const order: Record<Incident["status"], number> = {
    open: 0,
    vendor_escalated: 1,
    investigating: 2,
    resolved: 3,
  };
  const sorted = [...incidents].sort(
    (a, b) => order[a.status] - order[b.status] || b.openedAt.getTime() - a.openedAt.getTime()
  );

  const active = incidents.filter((i) => i.status !== "resolved");
  const breached = active.filter((i) => slaState(i, now).breached);
  const writable = hasDatabase();

  return (
    <>
      <PageHeader
        title="Incidents"
        subtitle="Tracked operational issues with owners, SLA timers, and a work log. Recurring alerts auto-create incidents; SLA breaches auto-escalate."
      />

      {/* Workflow stat cards. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active" value={active.length} />
        <StatCard
          label="SLA breached"
          value={breached.length}
          tone={breached.length > 0 ? "critical" : "good"}
        />
        <StatCard
          label="Vendor escalated"
          value={incidents.filter((i) => i.status === "vendor_escalated").length}
        />
        <StatCard
          label="Resolved"
          value={incidents.filter((i) => i.status === "resolved").length}
          tone="good"
        />
      </div>

      {/* Mock-mode hint: forms render but writes need a database. */}
      {!writable && (
        <Card className="mt-6 p-4 text-sm text-muted">
          Running on mock data — connect a database (DATABASE_URL) to create,
          assign, and update incidents.
        </Card>
      )}

      {/* The incident list. <details> gives expand/collapse with zero client JS. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          All incidents ({incidents.length})
        </div>
        {sorted.length === 0 ? (
          <EmptyState message="No incidents. Create one from any alert on the Alerts page." />
        ) : (
          <ul className="divide-y divide-border">
            {sorted.map((incident) => {
              const sla = slaState(incident, now);
              const incidentNotes = notesByIncident.get(incident.id) ?? [];
              return (
                <li key={incident.id}>
                  <details className="group">
                    {/* Summary row — always visible, click to expand. */}
                    <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3 hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
                      <SeverityBadge severity={incident.severity} />
                      <span className="min-w-0 flex-1 text-sm font-medium">
                        {incident.title}
                      </span>
                      {/* Workflow status chip. */}
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset",
                          STATUS_STYLE[incident.status]
                        )}
                      >
                        {incident.status.replace(/_/g, " ")}
                      </span>
                      {/* SLA chip — red when breached, muted otherwise. */}
                      {incident.status !== "resolved" && (
                        <span
                          className={cn(
                            "rounded-full px-2.5 py-0.5 text-xs font-medium",
                            sla.breached
                              ? "bg-critical-bg text-critical"
                              : "bg-surface-2 text-muted"
                          )}
                        >
                          {formatSla(sla)}
                        </span>
                      )}
                      <span className="text-xs text-muted">
                        {incident.owner ?? "unassigned"}
                      </span>
                    </summary>

                    {/* Expanded body: context, work log, and the action forms. */}
                    <div className="border-t border-border bg-surface-2/40 px-4 py-4">
                      <div className="text-sm text-muted">
                        {incident.summary ?? "No summary."}
                        {" · "}
                        {incident.propertyId ? (
                          <Link
                            href={`/properties/${incident.propertyId}`}
                            className="hover:text-primary"
                          >
                            {propName.get(incident.propertyId) ?? "—"}
                          </Link>
                        ) : (
                          "Portfolio-wide"
                        )}
                        {" · opened "}
                        {timeAgo(incident.openedAt)}
                        {incident.category && (
                          <span className="ml-2 rounded bg-surface-2 px-1.5 py-0.5 text-xs capitalize">
                            {incident.category.replace(/_/g, " ")}
                          </span>
                        )}
                      </div>

                      {/* Work log. */}
                      <div className="mt-3">
                        <div className="text-xs font-medium uppercase tracking-wide text-muted">
                          Notes ({incidentNotes.length})
                        </div>
                        <ul className="mt-2 space-y-2">
                          {incidentNotes.map((note) => (
                            <li key={note.id} className="rounded-lg bg-surface px-3 py-2 text-sm">
                              <span className="font-medium">{note.author}</span>{" "}
                              <span className="text-xs text-muted">{timeAgo(note.createdAt)}</span>
                              <div className="mt-0.5 text-muted">{note.body}</div>
                            </li>
                          ))}
                          {incidentNotes.length === 0 && (
                            <li className="text-sm text-muted">No notes yet.</li>
                          )}
                        </ul>
                        {/* Add-note form (server action). */}
                        {writable && (
                          <form action={addIncidentNote} className="mt-2 flex gap-2">
                            <input type="hidden" name="incidentId" value={incident.id} />
                            <input
                              name="body"
                              required
                              placeholder="Add a note…"
                              className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm"
                            />
                            <button className="rounded-lg bg-surface-2 px-3 py-1.5 text-xs font-medium hover:bg-border">
                              Add note
                            </button>
                          </form>
                        )}
                      </div>

                      {/* Assign / status form (server action). */}
                      {writable && (
                        <form action={updateIncident} className="mt-3 flex flex-wrap items-center gap-2">
                          <input type="hidden" name="id" value={incident.id} />
                          <input
                            name="owner"
                            defaultValue={incident.owner ?? ""}
                            placeholder="Assign owner…"
                            className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm"
                          />
                          <select
                            name="status"
                            defaultValue={incident.status}
                            className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm"
                          >
                            {incidentStatus.enumValues.map((s) => (
                              <option key={s} value={s}>
                                {s.replace(/_/g, " ")}
                              </option>
                            ))}
                          </select>
                          <button className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-fg hover:opacity-90">
                            Save
                          </button>
                        </form>
                      )}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
