// Data reads (mock or Postgres, chosen automatically).
import {
  getVendors,
  getProjects,
  getProperties,
  getCircuits,
  getProjectMilestones,
  getProjectChecklist,
} from "@/lib/queries";
// Pure helpers: contract warnings + progress math.
import {
  contractExpiringSoon,
  contractExpired,
  milestoneProgress,
  checklistProgress,
} from "@/lib/projects";
// Server actions for the milestone/checklist toggles (DB mode only).
import { toggleMilestone, toggleChecklistItem } from "@/app/actions/projects";
import { hasDatabase } from "@/db/client";
// Shared layout + badge components.
import { PageHeader, StatCard, Card, Table, Th, Td } from "@/components/ui";
import { StatusBadge } from "@/components/badges";
import { cn } from "@/lib/utils";
import type { Project, ProjectMilestone, ProjectChecklistItem } from "@/db/schema";

// Visual style per project lifecycle status.
const STATUS_STYLE: Record<Project["status"], string> = {
  planning: "bg-info-bg text-info ring-info/20",
  in_progress: "bg-warning-bg text-warning ring-warning/20",
  blocked: "bg-critical-bg text-critical ring-critical/20",
  completed: "bg-good-bg text-good ring-good/20",
};

// Compact date formatting for tables.
function fmtDate(dt: Date | null) {
  if (!dt) return "—";
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// Vendor & project management: projects with milestones + cutover/validation
// checklists, the telecom circuit inventory, and full vendor records
// (contacts, escalation paths, contract windows, SLA terms).
export default async function VendorsPage() {
  const [vendors, projects, properties, circuits, milestones, checklist] =
    await Promise.all([
      getVendors(),
      getProjects(),
      getProperties(),
      getCircuits(),
      getProjectMilestones(),
      getProjectChecklist(),
    ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  const vendorName = new Map(vendors.map((v) => [v.id, v.name]));
  // Group milestones/checklist items by project for fast lookup while rendering.
  const msByProject = new Map<string, ProjectMilestone[]>();
  for (const m of milestones)
    msByProject.set(m.projectId, [...(msByProject.get(m.projectId) ?? []), m]);
  const clByProject = new Map<string, ProjectChecklistItem[]>();
  for (const c of checklist)
    clByProject.set(c.projectId, [...(clByProject.get(c.projectId) ?? []), c]);

  const now = new Date();
  const writable = hasDatabase();
  const activeProjects = projects.filter((p) => p.status !== "completed");
  const overdue = activeProjects.filter((p) => p.dueDate && p.dueDate < now);
  // Renewal radar: vendor contracts + circuit contracts ending within 90 days.
  const expiringContracts =
    vendors.filter((v) => contractExpiringSoon(v.contractEnd, now)).length +
    circuits.filter((c) => contractExpiringSoon(c.contractEnd, now)).length;
  const circuitIssues = circuits.filter((c) => c.status !== "online").length;

  return (
    <>
      <PageHeader
        title="Vendors & Projects"
        subtitle="MSPs, carriers, and hardware partners — contracts, SLAs, circuits, rollouts, and go-live checklists."
      />

      {/* Rollup stat cards. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active projects" value={activeProjects.length} />
        <StatCard
          label="Overdue"
          value={overdue.length}
          tone={overdue.length > 0 ? "critical" : "good"}
        />
        <StatCard
          label="Circuits"
          value={circuits.length}
          hint={`${circuitIssues} degraded/offline`}
          tone={circuitIssues > 0 ? "warning" : "good"}
        />
        <StatCard
          label="Contracts ending ≤90d"
          value={expiringContracts}
          tone={expiringContracts > 0 ? "warning" : "good"}
        />
      </div>

      {/* Projects with expandable milestones + checklists. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Projects ({projects.length})
        </div>
        <ul className="divide-y divide-border">
          {projects.map((p) => {
            const ms = msByProject.get(p.id) ?? [];
            const cl = clByProject.get(p.id) ?? [];
            const cutover = cl.filter((i) => i.phase === "cutover");
            const validation = cl.filter((i) => i.phase === "validation");
            const progress = milestoneProgress(ms);
            const isOverdue = p.dueDate && p.status !== "completed" && p.dueDate < now;
            return (
              <li key={p.id}>
                <details className="group">
                  {/* Summary row. */}
                  <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3 hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
                    <span className="min-w-0 flex-1">
                      <span className="text-sm font-medium">{p.name}</span>
                      <span className="ml-2 text-xs text-muted">
                        {p.propertyId ? propName.get(p.propertyId) : "Portfolio-wide"}
                        {p.vendorId && ` · ${vendorName.get(p.vendorId)}`}
                      </span>
                    </span>
                    {/* Milestone progress, when the project has milestones. */}
                    {progress.total > 0 && (
                      <span className="text-xs tabular-nums text-muted">
                        {progress.done}/{progress.total} milestones
                      </span>
                    )}
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset",
                        STATUS_STYLE[p.status]
                      )}
                    >
                      {p.status.replace(/_/g, " ")}
                    </span>
                    <span className={cn("text-xs", isOverdue ? "font-medium text-critical" : "text-muted")}>
                      due {fmtDate(p.dueDate)}
                      {isOverdue && " (overdue)"}
                    </span>
                  </summary>

                  {/* Expanded: description, milestones, cutover + validation checklists. */}
                  <div className="border-t border-border bg-surface-2/40 px-4 py-4">
                    {p.description && <p className="text-sm text-muted">{p.description}</p>}

                    {/* Milestones with toggle buttons. */}
                    {ms.length > 0 && (
                      <div className="mt-3">
                        <div className="text-xs font-medium uppercase tracking-wide text-muted">
                          Milestones ({progress.pct}%)
                        </div>
                        <ul className="mt-2 space-y-1.5">
                          {ms.map((m) => (
                            <li key={m.id} className="flex items-center gap-2 text-sm">
                              {writable ? (
                                <form action={toggleMilestone}>
                                  <input type="hidden" name="id" value={m.id} />
                                  <button
                                    className={cn(
                                      "flex h-4 w-4 items-center justify-center rounded border text-[10px] leading-none",
                                      m.completedAt
                                        ? "border-good bg-good text-white"
                                        : "border-border bg-surface"
                                    )}
                                    aria-label="toggle milestone"
                                  >
                                    {m.completedAt ? "✓" : ""}
                                  </button>
                                </form>
                              ) : (
                                <span className={cn("h-4 w-4 rounded border text-center text-[10px] leading-4", m.completedAt ? "border-good bg-good text-white" : "border-border")}>
                                  {m.completedAt ? "✓" : ""}
                                </span>
                              )}
                              <span className={m.completedAt ? "text-muted line-through" : ""}>
                                {m.name}
                              </span>
                              <span className="ml-auto text-xs text-muted">
                                {m.completedAt ? `done ${fmtDate(m.completedAt)}` : `due ${fmtDate(m.dueDate)}`}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Cutover + validation checklists. */}
                    {[
                      { title: "Cutover checklist", items: cutover },
                      { title: "Post-deployment validation", items: validation },
                    ].map(
                      ({ title, items }) =>
                        items.length > 0 && (
                          <div key={title} className="mt-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-muted">
                              {title} ({checklistProgress(items).done}/{items.length})
                            </div>
                            <ul className="mt-2 space-y-1.5">
                              {items.map((item) => (
                                <li key={item.id} className="flex items-center gap-2 text-sm">
                                  {writable ? (
                                    <form action={toggleChecklistItem}>
                                      <input type="hidden" name="id" value={item.id} />
                                      <button
                                        className={cn(
                                          "flex h-4 w-4 items-center justify-center rounded border text-[10px] leading-none",
                                          item.done === 1
                                            ? "border-good bg-good text-white"
                                            : "border-border bg-surface"
                                        )}
                                        aria-label="toggle checklist item"
                                      >
                                        {item.done === 1 ? "✓" : ""}
                                      </button>
                                    </form>
                                  ) : (
                                    <span className={cn("h-4 w-4 rounded border text-center text-[10px] leading-4", item.done === 1 ? "border-good bg-good text-white" : "border-border")}>
                                      {item.done === 1 ? "✓" : ""}
                                    </span>
                                  )}
                                  <span className={item.done === 1 ? "text-muted line-through" : ""}>
                                    {item.label}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )
                    )}
                  </div>
                </details>
              </li>
            );
          })}
        </ul>
      </Card>

      {/* Telecom circuit inventory. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Circuit inventory ({circuits.length})
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Circuit</Th>
              <Th>Property</Th>
              <Th>Carrier</Th>
              <Th>Type</Th>
              <Th className="text-right">Bandwidth</Th>
              <Th>Status</Th>
              <Th className="text-right">$/mo</Th>
              <Th className="text-right">Contract end</Th>
            </tr>
          </thead>
          <tbody>
            {circuits.map((c) => {
              const expiring = contractExpiringSoon(c.contractEnd, now);
              const expired = contractExpired(c.contractEnd, now);
              return (
                <tr key={c.id} className="hover:bg-surface-2">
                  <Td className="font-medium">{c.circuitRef}</Td>
                  <Td className="text-muted">{propName.get(c.propertyId) ?? "—"}</Td>
                  <Td className="text-muted">{c.vendorId ? vendorName.get(c.vendorId) : "—"}</Td>
                  <Td className="text-muted">{c.type}</Td>
                  <Td className="text-right tabular-nums">{c.bandwidthMbps} Mbps</Td>
                  <Td><StatusBadge status={c.status} /></Td>
                  <Td className="text-right tabular-nums">{c.monthlyCost ?? "—"}</Td>
                  <Td className={cn("text-right", (expiring || expired) && "font-medium text-warning")}>
                    {fmtDate(c.contractEnd)}
                    {expired ? " (expired)" : expiring ? " (≤90d)" : ""}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>

      {/* Vendor records: contacts, escalation paths, contracts, SLA terms. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Vendors ({vendors.length})
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Vendor</Th>
              <Th>Category</Th>
              <Th>Contact</Th>
              <Th>Escalation path</Th>
              <Th>Contract</Th>
              <Th>SLA terms</Th>
            </tr>
          </thead>
          <tbody>
            {vendors.map((v) => {
              const expiring = contractExpiringSoon(v.contractEnd, now);
              return (
                <tr key={v.id} className="hover:bg-surface-2">
                  <Td className="font-medium">{v.name}</Td>
                  <Td className="text-muted">{v.category}</Td>
                  <Td>
                    <div>{v.contactName}</div>
                    <div className="text-xs text-muted">
                      {v.contactEmail} · {v.contactPhone}
                    </div>
                  </Td>
                  <Td className="text-muted">{v.escalationContact ?? "—"}</Td>
                  <Td className={cn(expiring && "font-medium text-warning")}>
                    {fmtDate(v.contractStart)} → {fmtDate(v.contractEnd)}
                    {expiring && (
                      <div className="text-xs font-medium text-warning">renews ≤90d</div>
                    )}
                  </Td>
                  <Td className="text-muted">{v.slaTerms ?? "—"}</Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
