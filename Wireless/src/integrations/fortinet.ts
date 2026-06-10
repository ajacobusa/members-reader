import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
import { NotImplemented } from "./not-implemented";

/**
 * Fortinet adapter (FortiGate-managed FortiAPs). LIVE mode uses the FortiGate
 * REST API with a bearer API token; FortiManager ADOMs can expose multiple
 * sites. A single FortiGate is treated as one site.
 */
export class FortinetAdapter implements VendorAdapter {
  readonly vendor = "fortinet" as const;
  readonly displayName = "Fortinet";
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(creds?.baseUrl && creds?.apiKey /* REST API token */);
  }

  async testConnection() {
    if (!this.live) return true;
    // LIVE: GET {baseUrl}/api/v2/monitor/system/status  (Bearer token)
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor);
    // LIVE (FortiManager): GET /api/v2/cmdb/system/admin/... ADOMs/devices
    // LIVE (single FortiGate): one site = the device itself
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (FortiGate monitor API), normalize:
    //   GET /api/v2/monitor/wifi/managed_ap   -> access points (+ firmware)
    //   GET /api/v2/monitor/wifi/client       -> clients
    //   GET /api/v2/monitor/system/fortiguard / event log -> alerts
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
