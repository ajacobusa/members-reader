// Shared contract + data shapes this adapter conforms to.
import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
// Generic mock helpers used in MOCK mode.
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
// Error thrown by LIVE methods not yet wired to the real API.
import { NotImplemented } from "./not-implemented";

/**
 * Ubiquiti UniFi adapter. LIVE mode targets either the UniFi Site Manager API
 * (cloud, `X-API-KEY` header) or a self-hosted Network controller (cookie login).
 */
export class UniFiAdapter implements VendorAdapter {
  // Machine id for this vendor.
  readonly vendor = "unifi" as const;
  // Friendly name shown in the UI.
  readonly displayName = "Ubiquiti UniFi";
  // True when we have credentials for either of UniFi's two access methods.
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    // LIVE if EITHER a cloud API key is present, OR a full self-hosted
    // controller login (baseUrl + username + password) is present.
    this.live = Boolean(creds?.apiKey || (creds?.baseUrl && creds?.username && creds?.password));
  }

  async testConnection() {
    if (!this.live) return true; // MOCK: always "connected".
    // LIVE (Site Manager): GET {baseUrl}/v1/sites  with X-API-KEY
    // ^ A successful response confirms the cloud API key. Not built yet:
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor); // MOCK: canned site list.
    // LIVE (Site Manager): GET {baseUrl}/v1/sites
    // LIVE (controller):  GET {baseUrl}/api/self/sites
    // ^ Different endpoint depending on cloud vs self-hosted. Not built yet:
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    // MOCK: build a fake snapshot for this site id.
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (controller), normalize:
    //   GET /api/s/{site}/stat/device   -> access points (+ firmware)
    //   GET /api/s/{site}/stat/sta      -> clients (guest flag in record)
    //   GET /api/s/{site}/stat/alarm    -> alerts
    // ^ Fetch each, normalize, and bundle into one snapshot. Not built yet:
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
