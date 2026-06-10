import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
import { NotImplemented } from "./not-implemented";

/**
 * Juniper Mist adapter. LIVE mode uses the Mist Cloud API (token header
 * `Authorization: Token <apitoken>`). Org sites map directly to our "sites".
 */
export class MistAdapter implements VendorAdapter {
  readonly vendor = "mist" as const;
  readonly displayName = "Juniper Mist";
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(creds?.apiKey && creds?.customerId /* orgId */);
  }

  async testConnection() {
    if (!this.live) return true;
    // LIVE: GET {baseUrl}/api/v1/self  (token valid?)
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor);
    // LIVE: GET {baseUrl}/api/v1/orgs/{orgId}/sites
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (Mist), normalize:
    //   GET /api/v1/sites/{siteId}/stats/devices?type=ap  -> access points
    //   GET /api/v1/sites/{siteId}/stats/clients          -> clients
    //   GET /api/v1/sites/{siteId}/alarms                  -> alerts
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
