import Link from "next/link";
import { getPortfolio } from "@/lib/queries";
import { PageHeader, Card, Table, Th, Td } from "@/components/ui";
import { HealthScore, VendorBadge } from "@/components/badges";

export default async function PropertiesPage() {
  const portfolio = await getPortfolio();

  return (
    <>
      <PageHeader
        title="Properties"
        subtitle="Every site in the portfolio with live health and inventory counts."
      />
      <Card>
        <Table>
          <thead>
            <tr>
              <Th>Property</Th>
              <Th>Location</Th>
              <Th>Vendor</Th>
              <Th className="text-right">APs</Th>
              <Th className="text-right">Clients</Th>
              <Th className="text-right">IoT</Th>
              <Th className="text-right">Open alerts</Th>
              <Th className="text-right">Health</Th>
            </tr>
          </thead>
          <tbody>
            {portfolio.map((p) => (
              <tr key={p.property.id} className="hover:bg-surface-2">
                <Td>
                  <Link
                    href={`/properties/${p.property.id}`}
                    className="font-medium text-foreground hover:text-primary"
                  >
                    {p.property.name}
                  </Link>
                </Td>
                <Td className="text-muted">
                  {p.property.city}, {p.property.region}
                </Td>
                <Td>
                  <VendorBadge vendor={p.property.managedBy} />
                </Td>
                <Td className="text-right tabular-nums">
                  {p.apCount - p.apOffline}/{p.apCount}
                </Td>
                <Td className="text-right tabular-nums">{p.clientCount}</Td>
                <Td className="text-right tabular-nums">{p.iotCount}</Td>
                <Td className="text-right tabular-nums">{p.openAlerts}</Td>
                <Td className="text-right">
                  <HealthScore score={p.health.score} band={p.health.band} size="sm" />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}
