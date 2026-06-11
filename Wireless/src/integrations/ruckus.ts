// Shared contract + data shapes this adapter conforms to.
import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
// Generic mock helpers used in MOCK mode.
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
// Error thrown by LIVE methods not yet wired to the real API.
import { NotImplemented } from "./not-implemented";

/**
 * RUCKUS adapter. LIVE mode targets SmartZone (session-token REST API) or
 * RUCKUS One (OAuth2). Zones/venues map to our "sites".
 */
export class RuckusAdapter implements VendorAdapter {
  // Machine id for this vendor.
  readonly vendor = "ruckus" as const;
  // Friendly name shown in the UI.
  readonly displayName = "RUCKUS";
  // True when we have enough credentials to reach a RUCKUS controller.
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    // LIVE requires a baseUrl AND either an API key OR a username/password pair.
    this.live = Boolean(creds?.baseUrl && (creds?.apiKey || (creds?.username && creds?.password)));
  }

  async testConnection() {
    if (!this.live) return true; // MOCK: always "connected".
    // LIVE (SmartZone): POST {baseUrl}/wsg/api/public/v11_1/session  -> service ticket
    // ^ Logging in returns a session "ticket" used for later calls. Not built yet:
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor); // MOCK: canned site list.
    // LIVE (SmartZone): GET {baseUrl}/wsg/api/public/v11_1/zones
    // LIVE (RUCKUS One): GET {baseUrl}/venues
    // ^ Zones (SmartZone) or venues (RUCKUS One) become our sites. Not built yet:
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    // MOCK: build a fake snapshot for this site id.
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (SmartZone), normalize:
    //   GET /wsg/api/public/v11_1/aps          -> access points
    //   GET /wsg/api/public/v11_1/clients      -> clients
    //   GET /wsg/api/public/v11_1/alarms       -> alerts
    // ^ Fetch each, normalize, and bundle into one snapshot. Not built yet:
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
