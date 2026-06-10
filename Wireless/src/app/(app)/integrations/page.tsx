import { getIntegrations, getProperties } from "@/lib/queries";
import { supportedVendors } from "@/integrations/registry";
import { integrationVendor } from "@/db/schema";
import { PageHeader, Card } from "@/components/ui";
import { VENDOR_LABELS } from "@/components/badges";
import { cn, timeAgo } from "@/lib/utils";
import { Plug, CheckCircle2, Clock } from "lucide-react";

export default async function IntegrationsPage() {
  const [integrations, properties] = await Promise.all([
    getIntegrations(),
    getProperties(),
  ]);
  const supported = new Set(supportedVendors());
  const allVendors = integrationVendor.enumValues;
  const configured = new Map(integrations.map((i) => [i.vendor, i]));
  const siteCount = new Map<string, number>();
  for (const p of properties) {
    if (p.managedBy) siteCount.set(p.managedBy, (siteCount.get(p.managedBy) ?? 0) + 1);
  }

  return (
    <>
      <PageHeader
        title="Integrations"
        subtitle="Network vendor connections. Aruba Central first; others drop in behind the same adapter interface."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {allVendors.map((vendor) => {
          const integration = configured.get(vendor);
          const isSupported = supported.has(vendor);
          const connected = integration?.status === "connected";
          return (
            <Card key={vendor} className="p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-lg",
                      connected ? "bg-good-bg text-good" : "bg-surface-2 text-muted"
                    )}
                  >
                    <Plug className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold">{VENDOR_LABELS[vendor]}</div>
                    <div className="text-xs text-muted">
                      {isSupported ? "Adapter available" : "Planned"}
                    </div>
                  </div>
                </div>
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
              {integration && (
                <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                  <div>{integration.label}</div>
                  <div className="mt-1 flex items-center justify-between">
                    <span>Last synced: {timeAgo(integration.lastSyncedAt)}</span>
                    <span>{siteCount.get(vendor) ?? 0} sites</span>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <Card className="mt-6 p-4">
        <div className="text-sm font-semibold">How syncing works</div>
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
