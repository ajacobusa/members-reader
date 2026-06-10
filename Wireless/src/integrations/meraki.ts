import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
import { NotImplemented } from "./not-implemented";

/**
 * Cisco Meraki adapter. LIVE mode uses the Meraki Dashboard API (REST + API key
 * header `X-Cisco-Meraki-API-Key`). Networks map to our "sites".
 */
export class MerakiAdapter implements VendorAdapter {
  readonly vendor = "meraki" as const;
  readonly displayName = "Cisco Meraki";
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(creds?.apiKey && creds?.customerId /* organizationId */);
  }

  async testConnection() {
    if (!this.live) return true;
    // LIVE: GET {baseUrl}/organizations  (200 => key valid)
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor);
    // LIVE: GET {baseUrl}/organizations/{organizationId}/networks
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE: combine and normalize:
    //   GET /networks/{id}/devices                          -> access points
    //   GET /networks/{id}/clients                          -> clients (guest via SSID/policy)
    //   GET /organizations/{orgId}/assurance/alerts         -> alerts
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
