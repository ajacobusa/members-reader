// The audit trail reader + the live access model.
import { getAuditEntries } from "@/lib/audit";
import { getActor, permissionMatrix, ROLES, ACTIONS } from "@/lib/authz";
import { hasDatabase } from "@/db/client";
// Shared layout components.
import { PageHeader, Card, Table, Th, Td, EmptyState } from "@/components/ui";
import { timeAgo, cn } from "@/lib/utils";

// Security page: current access mode, the role → permission matrix (rendered
// straight from the code so it can't drift), and the audit/change-history log
// including login activity once Clerk webhooks are configured.
export default async function AuditPage() {
  const [entries, actor] = await Promise.all([getAuditEntries(50), getActor()]);
  const clerkOn = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
  const matrix = permissionMatrix();

  return (
    <>
      <PageHeader
        title="Security & Audit"
        subtitle="Who can do what, and who did what — RBAC model, change history, and login activity."
      />

      {/* Current mode + actor. */}
      <Card className="p-4">
        <div className="text-sm font-semibold">Access mode</div>
        <p className="mt-2 text-sm text-muted">
          {clerkOn ? (
            <>Authentication is <span className="font-medium text-good">enforced</span> (Clerk). Users resolve to a role via memberships; the first sign-in bootstraps as Owner.</>
          ) : (
            <>Running in <span className="font-medium text-warning">dev mode</span> — auth off, every request acts as Owner. Add Clerk keys to enforce sign-in and roles.</>
          )}{" "}
          Current actor: <span className="font-medium text-foreground">{actor.name}</span>{" "}
          (<span className="capitalize">{actor.role.replace(/_/g, " ")}</span>
          {actor.propertyIds === null ? ", all properties" : `, ${actor.propertyIds.length} properties`}).
          Vendor API credentials are stored AES-256-GCM encrypted.
        </p>
      </Card>

      {/* The permission matrix, rendered from the same constant the code enforces. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Access model — role × permission
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Role</Th>
              {ACTIONS.map((a) => (
                <Th key={a} className="text-center">{a}</Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROLES.map((role) => (
              <tr key={role} className="hover:bg-surface-2">
                <Td className="font-medium capitalize">{role.replace(/_/g, " ")}</Td>
                {ACTIONS.map((a) => (
                  <Td key={a} className="text-center">
                    {matrix[role].includes(a) ? (
                      <span className="text-good">✓</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </Td>
                ))}
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {/* The audit log: writes, automation, maintenance, and auth events. */}
      <Card className="mt-6">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Audit log (latest {entries.length})
        </div>
        {!hasDatabase() ? (
          <EmptyState message="Running on mock data — connect a database to record audit history." />
        ) : entries.length === 0 ? (
          <EmptyState message="No audit entries yet. Actions, syncs, and logins will appear here." />
        ) : (
          <ul className="divide-y divide-border">
            {entries.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
                {/* Auth events get a distinct chip so login activity stands out. */}
                <span
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs font-medium",
                    e.action.startsWith("auth.")
                      ? "bg-info-bg text-info"
                      : e.role === "system"
                        ? "bg-surface-2 text-muted"
                        : "bg-good-bg text-good"
                  )}
                >
                  {e.action}
                </span>
                <span className="font-medium">{e.actorName ?? e.actorId}</span>
                {e.role && <span className="text-xs capitalize text-muted">{e.role.replace(/_/g, " ")}</span>}
                {e.target && <span className="text-xs text-muted">{e.target}</span>}
                {/* Change history: compact JSON of before/after details. */}
                {e.details && (
                  <code className="max-w-md truncate rounded bg-surface-2 px-1.5 py-0.5 text-xs text-muted">
                    {JSON.stringify(e.details)}
                  </code>
                )}
                <span className="ml-auto shrink-0 text-xs text-muted">{timeAgo(e.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
