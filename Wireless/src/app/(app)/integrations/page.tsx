// Queries: the configured integrations and all properties (to count sites per vendor).
import { getIntegrations, getProperties } from "@/lib/queries";
// Returns the list of vendors we actually have working adapters for.
import { supportedVendors } from "@/integrations/registry";
// The database enum listing every possible integration vendor (supported or planned).
import { integrationVendor } from "@/db/schema";
// Shared layout pieces.
import { PageHeader, Card } from "@/components/ui";
// A map from vendor key -> human-friendly display label.
import { VENDOR_LABELS } from "@/components/badges";
// Class-name joiner and timestamp formatter utilities.
import { cn, timeAgo } from "@/lib/utils";
// Icon components from the lucide-react icon library.
import { Plug, CheckCircle2, Clock } from "lucide-react";

// Server component showing one card per vendor and its connection state.
export default async function IntegrationsPage() {
  // Fetch configured integrations and properties in parallel.
  const [integrations, properties] = await Promise.all([
    getIntegrations(),
    getProperties(),
  ]);
  // A Set of vendor keys we have adapters for, for fast "is this supported?" checks.
  const supported = new Set(supportedVendors());
  // Every vendor value defined in the schema enum (the full list to render cards for).
  const allVendors = integrationVendor.enumValues;
  // Map from vendor key -> its integration record, so we can look up config by vendor.
  const configured = new Map(integrations.map((i) => [i.vendor, i]));
  // Will hold a count of how many properties are managed by each vendor.
  const siteCount = new Map<string, number>();
  // Tally site counts: for each property with a managing vendor, increment that vendor's count.
  for (const p of properties) {
    if (p.managedBy) siteCount.set(p.managedBy, (siteCount.get(p.managedBy) ?? 0) + 1);
  }

  // Fragment wrapper for the header, the vendor card grid, and the explainer card.
  return (
    <>
      {/* Page header. */}
      <PageHeader
        title="Integrations"
        subtitle="Network vendor connections. Aruba Central first; others drop in behind the same adapter interface."
      />

      {/* Responsive grid of vendor cards: 1 column on phones, 2 on tablets, 3 on desktops. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Render one card for every vendor in the schema enum. */}
        {allVendors.map((vendor) => {
          // The integration record for this vendor, if one has been configured.
          const integration = configured.get(vendor);
          // Whether we have a working adapter for this vendor.
          const isSupported = supported.has(vendor);
          // Whether this vendor is currently connected (status === "connected").
          const connected = integration?.status === "connected";
          return (
            <Card key={vendor} className="p-4">
              {/* Top row of the card: icon + labels on the left, status pill on the right. */}
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  {/* Plug icon tile; green background when connected, muted otherwise. */}
                  <div
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-lg",
                      connected ? "bg-good-bg text-good" : "bg-surface-2 text-muted"
                    )}
                  >
                    <Plug className="h-5 w-5" />
                  </div>
                  <div>
                    {/* Human-friendly vendor name. */}
                    <div className="text-sm font-semibold">{VENDOR_LABELS[vendor]}</div>
                    {/* Sub-label: whether an adapter exists yet or is merely planned. */}
                    <div className="text-xs text-muted">
                      {isSupported ? "Adapter available" : "Planned"}
                    </div>
                  </div>
                </div>
                {/* Right-side status: a green "Connected" badge, or a muted "Not configured"/"Soon". */}
                {connected ? (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-good">
                    <CheckCircle2 className="h-4 w-4" /> Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-muted">
                    <Clock className="h-4 w-4" /> {isSupported ? "Not configured" : "Soon"}
                  </span>
                )}
              </div>
              {/* Extra detail block, only shown for vendors that have an integration record. */}
              {integration && (
                <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                  {/* The integration's configured label/name. */}
                  <div>{integration.label}</div>
                  <div className="mt-1 flex items-center justify-between">
                    {/* When the last sync happened, humanized. */}
                    <span>Last synced: {timeAgo(integration.lastSyncedAt)}</span>
                    {/* How many sites this vendor manages (0 if none). */}
                    <span>{siteCount.get(vendor) ?? 0} sites</span>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {/* Explainer card describing how the vendor sync architecture works. */}
      <Card className="mt-6 p-4">
        <div className="text-sm font-semibold">How syncing works</div>
        {/* Plain-language description of the adapter + background-job sync flow. */}
        <p className="mt-2 text-sm text-muted">
          Each vendor implements one <code className="text-foreground">VendorAdapter</code>{" "}
          interface. A background job (Inngest) pulls a normalized snapshot —
          access points, clients, IoT devices, and alerts — and upserts it into
          Postgres, then recomputes each property&apos;s health score. Adding
          Meraki, UniFi, Ruckus, Fortinet, or Mist is a new adapter class plus one
          line in the registry; nothing else changes.
        </p>
      </Card>
    </>
  );
}
