// The shared Inngest client this function registers against.
import { inngest } from "./client";
// The real sync pipeline (adapter → normalize → upsert into Postgres).
import { syncAll } from "@/lib/sync";
// Union of valid vendor id strings, for typing the event payload.
import type { IntegrationVendorName } from "@/db/schema";

/**
 * Vendor sync job. Trigger by sending the "vendor/sync.requested" event —
 * optionally with { data: { vendor: "aruba_central" } } to sync one vendor;
 * omit to sync every configured integration.
 *
 * The heavy lifting lives in lib/sync.ts (same code the /api/admin/sync
 * endpoint uses), so manual triggers and background jobs behave identically.
 * Inngest adds durability: retries with backoff on failure.
 */
export const syncVendor = inngest.createFunction(
  { id: "sync-vendor", retries: 3, triggers: [{ event: "vendor/sync.requested" }] },
  async ({ event, step }) => {
    // Narrow the optional event payload to a vendor filter.
    const vendor = event.data?.vendor as IntegrationVendorName | undefined;
    // One durable step: the pipeline records per-integration outcomes itself
    // (sync_runs + integrations.lastError), so partial failures are visible.
    // The summary includes what the post-sync ticketing automation did.
    const summary = await step.run("sync-all", () => syncAll(vendor));
    return summary;
  }
);

// Every function the /api/inngest endpoint serves.
export const functions = [syncVendor];
