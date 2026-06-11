// Shared contract + data shapes this adapter conforms to.
import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
// Generic mock helpers (shared across most vendors) for MOCK mode.
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
// Error thrown by LIVE methods not yet wired to the real API.
import { NotImplemented } from "./not-implemented";

/**
 * Cisco Meraki adapter. LIVE mode uses the Meraki Dashboard API (REST + API key
 * header `X-Cisco-Meraki-API-Key`). Networks map to our "sites".
 */
export class MerakiAdapter implements VendorAdapter {
  // Machine id for this vendor (`as const` pins the exact literal).
  readonly vendor = "meraki" as const;
  // Friendly name shown in the UI.
  readonly displayName = "Cisco Meraki";
  // True when we have enough credentials to talk to the real API.
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    // Meraki needs an API key plus an organization id (stored in customerId).
    this.live = Boolean(creds?.apiKey && creds?.customerId /* organizationId */);
  }

  async testConnection() {
    if (!this.live) return true; // MOCK: pretend we're connected.
    // LIVE: GET {baseUrl}/organizations  (200 => key valid)
    // ^ A 200 response would confirm the API key works. Not built yet:
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor); // MOCK: canned site list.
    // LIVE: GET {baseUrl}/organizations/{organizationId}/networks
    // ^ Meraki "networks" become our sites. Not built yet:
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    // MOCK: build a fake snapshot for this site id.
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE: combine and normalize:
    //   GET /networks/{id}/devices                          -> access points
    //   GET /networks/{id}/clients                          -> clients (guest via SSID/policy)
    //   GET /organizations/{orgId}/assurance/alerts         -> alerts
    // ^ Fetch each, map into Normalized* shapes, bundle into one snapshot.
    //   Not built yet:
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
