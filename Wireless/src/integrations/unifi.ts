import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
import { NotImplemented } from "./not-implemented";

/**
 * Ubiquiti UniFi adapter. LIVE mode targets either the UniFi Site Manager API
 * (cloud, `X-API-KEY` header) or a self-hosted Network controller (cookie login).
 */
export class UniFiAdapter implements VendorAdapter {
  readonly vendor = "unifi" as const;
  readonly displayName = "Ubiquiti UniFi";
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(creds?.apiKey || (creds?.baseUrl && creds?.username && creds?.password));
  }

  async testConnection() {
    if (!this.live) return true;
    // LIVE (Site Manager): GET {baseUrl}/v1/sites  with X-API-KEY
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor);
    // LIVE (Site Manager): GET {baseUrl}/v1/sites
    // LIVE (controller):  GET {baseUrl}/api/self/sites
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (controller), normalize:
    //   GET /api/s/{site}/stat/device   -> access points (+ firmware)
    //   GET /api/s/{site}/stat/sta      -> clients (guest flag in record)
    //   GET /api/s/{site}/stat/alarm    -> alerts
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
