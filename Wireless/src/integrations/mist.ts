// Shared contract + data shapes this adapter conforms to.
import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
// Generic mock helpers used in MOCK mode.
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
// Error thrown by LIVE methods not yet wired to the real API.
import { NotImplemented } from "./not-implemented";

/**
 * Juniper Mist adapter. LIVE mode uses the Mist Cloud API (token header
 * `Authorization: Token <apitoken>`). Org sites map directly to our "sites".
 */
export class MistAdapter implements VendorAdapter {
  // Machine id for this vendor.
  readonly vendor = "mist" as const;
  // Friendly name shown in the UI.
  readonly displayName = "Juniper Mist";
  // True when we have the credentials needed to reach the Mist Cloud API.
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    // Mist needs an API token (apiKey) and an org id (stored in customerId).
    this.live = Boolean(creds?.apiKey && creds?.customerId /* orgId */);
  }

  async testConnection() {
    if (!this.live) return true; // MOCK: always "connected".
    // LIVE: GET {baseUrl}/api/v1/self  (token valid?)
    // ^ The /self endpoint returns the caller's account if the token is valid.
    //   Not built yet:
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor); // MOCK: canned site list.
    // LIVE: GET {baseUrl}/api/v1/orgs/{orgId}/sites
    // ^ Returns the sites under our org. Not built yet:
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    // MOCK: build a fake snapshot for this site id.
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (Mist), normalize:
    //   GET /api/v1/sites/{siteId}/stats/devices?type=ap  -> access points
    //   GET /api/v1/sites/{siteId}/stats/clients          -> clients
    //   GET /api/v1/sites/{siteId}/alarms                  -> alerts
    // ^ Fetch each, normalize, and bundle into one snapshot. Not built yet:
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
