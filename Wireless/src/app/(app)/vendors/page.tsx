import { getVendors, getProjects, getProperties } from "@/lib/queries";
import { PageHeader, Card, Table, Th, Td } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Project } from "@/db/schema";

const STATUS_STYLE: Record<Project["status"], string> = {
  planning: "bg-info-bg text-info ring-info/20",
  in_progress: "bg-warning-bg text-warning ring-warning/20",
  blocked: "bg-critical-bg text-critical ring-critical/20",
  completed: "bg-good-bg text-good ring-good/20",
};

function fmtDate(d: Date | null) {
  if (!d) return "—";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default async function VendorsPage() {
  const [vendors, projects, properties] = await Promise.all([
    getVendors(),
    getProjects(),
    getProperties(),
  ]);
  const propName = new Map(properties.map((p) => [p.id, p.name]));
  const today = new Date();

  return (
    <>
      <PageHeader
        title="Vendors & Projects"
        subtitle="MSPs, telecom, and hardware partners — plus active rollouts and their deadlines."
      />

      <Card>
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Projects ({projects.length})
        </div>
        <Table>
          <thead>
            <tr>
              <Th>Project</Th>
              <Th>Property</Th>
              <Th>Status</Th>
              <Th className="text-right">Due</Th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => {
              const overdue =
                p.dueDate && p.status !== "completed" && p.dueDate < today;
              return (
                <tr key={p.id} className="hover:bg-surface-2">
                  <Td>
                    <div className="font-medium">{p.name}</div>
                    {p.description && (
                      <div className="text-xs text-muted">{p.description}</div>
                    )}
                  </Td>
                  <Td className="text-muted">
                    {p.propertyId ? propName.get(p.propertyId) : "Portfolio-wide"}
                  </Td>
                  <Td>
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset",
                        STATUS_STYLE[p.status]
                      )}
                    >
                      {p.status.replace(/_/g, " ")}
                    </span>
                  </Td>
                  <Td className={cn("text-right", overdue && "font-medium text-critical")}>
                    {fmtDate(p.dueDate)}
                    {overdue && <span className="ml-1">(overdue)</span>}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </Card>

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
              <Th>Email</Th>
              <Th>Phone</Th>
            </tr>
          </thead>
          <tbody>
            {vendors.map((v) => (
              <tr key={v.id} className="hover:bg-surface-2">
                <Td className="font-medium">{v.name}</Td>
                <Td className="text-muted">{v.category}</Td>
                <Td>{v.contactName}</Td>
                <Td className="text-muted">{v.contactEmail}</Td>
                <Td className="text-muted">{v.contactPhone}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
