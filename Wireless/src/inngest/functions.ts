import { inngest } from "./client";
import { getAdapter } from "@/integrations/registry";
import type { IntegrationVendorName } from "@/db/schema";

/**
 * Vendor sync job. Triggered per-integration (event payload carries the vendor
 * and, in live mode, the integration id whose credentials to load).
 *
 * Each step is durable: if the function crashes mid-sync, Inngest replays from
 * the last completed step. Today it pulls normalized snapshots from the adapter
 * (mock data); the marked TODO is where the upsert into Postgres goes.
 */
export const syncVendor = inngest.createFunction(
  { id: "sync-vendor", retries: 3, triggers: [{ event: "vendor/sync.requested" }] },
  async ({ event, step }) => {
    const vendor = (event.data?.vendor ?? "aruba_central") as IntegrationVendorName;
    const adapter = getAdapter(vendor);

    const sites = await step.run("list-sites", () => adapter.listSites());

    const results: { site: string; aps: number; alerts: number }[] = [];
    for (const site of sites) {
      const snapshot = await step.run(`fetch-${site.externalId}`, () =>
        adapter.fetchSiteSnapshot(site.externalId)
      );
      // TODO(live): upsert snapshot into Postgres via Drizzle (access_points,
      // clients, iot_devices, alerts), then recompute property health score.
      results.push({
        site: snapshot.siteName,
        aps: snapshot.accessPoints.length,
        alerts: snapshot.alerts.length,
      });
    }

    return { vendor, sitesSynced: sites.length, results };
  }
);

export const functions = [syncVendor];
