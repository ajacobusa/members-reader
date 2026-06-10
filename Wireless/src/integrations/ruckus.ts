import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
import { NotImplemented } from "./not-implemented";

/**
 * RUCKUS adapter. LIVE mode targets SmartZone (session-token REST API) or
 * RUCKUS One (OAuth2). Zones/venues map to our "sites".
 */
export class RuckusAdapter implements VendorAdapter {
  readonly vendor = "ruckus" as const;
  readonly displayName = "RUCKUS";
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(creds?.baseUrl && (creds?.apiKey || (creds?.username && creds?.password)));
  }

  async testConnection() {
    if (!this.live) return true;
    // LIVE (SmartZone): POST {baseUrl}/wsg/api/public/v11_1/session  -> service ticket
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor);
    // LIVE (SmartZone): GET {baseUrl}/wsg/api/public/v11_1/zones
    // LIVE (RUCKUS One): GET {baseUrl}/venues
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (SmartZone), normalize:
    //   GET /wsg/api/public/v11_1/aps          -> access points
    //   GET /wsg/api/public/v11_1/clients      -> clients
    //   GET /wsg/api/public/v11_1/alarms       -> alerts
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
