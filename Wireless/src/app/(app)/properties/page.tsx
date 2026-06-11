// Next.js link component for fast client-side navigation.
import Link from "next/link";
// Query that returns every property plus its rolled-up health and inventory counts.
import { getPortfolio } from "@/lib/queries";
// Shared layout/UI pieces: page header, card container, and table elements.
import { PageHeader, Card, Table, Th, Td } from "@/components/ui";
// Badge components for showing a health score and the managing vendor.
import { HealthScore, VendorBadge } from "@/components/badges";

// Server component that lists all properties. Async so it can await the query.
export default async function PropertiesPage() {
  // Fetch the full portfolio once before rendering.
  const portfolio = await getPortfolio();

  // Fragment wrapper below lets us return the header and the card as siblings.
  return (
    <>
      {/* Page title and description. */}
      <PageHeader
        title="Properties"
        subtitle="Every site in the portfolio with live health and inventory counts."
      />
      {/* Card containing the single properties table. */}
      <Card>
        <Table>
          {/* Header row: one <Th> per column. Right-aligned columns hold numbers. */}
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
            {/* Render one table row for each property in the portfolio. */}
            {portfolio.map((p) => (
              // `key` is the property id so React can track rows across re-renders.
              <tr key={p.property.id} className="hover:bg-surface-2">
                {/* Property name, linking through to its detail page. */}
                <Td>
                  <Link
                    href={`/properties/${p.property.id}`}
                    className="font-medium text-foreground hover:text-primary"
                  >
                    {p.property.name}
                  </Link>
                </Td>
                {/* City and region. */}
                <Td className="text-muted">
                  {p.property.city}, {p.property.region}
                </Td>
                {/* Badge showing which vendor manages this property's network. */}
                <Td>
                  <VendorBadge vendor={p.property.managedBy} />
                </Td>
                {/* Online APs over total APs. */}
                <Td className="text-right tabular-nums">
                  {p.apCount - p.apOffline}/{p.apCount}
                </Td>
                {/* Number of connected client devices. */}
                <Td className="text-right tabular-nums">{p.clientCount}</Td>
                {/* Number of IoT devices. */}
                <Td className="text-right tabular-nums">{p.iotCount}</Td>
                {/* Number of currently open alerts. */}
                <Td className="text-right tabular-nums">{p.openAlerts}</Td>
                {/* Compact health-score badge. */}
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
