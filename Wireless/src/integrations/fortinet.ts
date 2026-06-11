// Shared contract + data shapes this adapter conforms to.
import type { VendorAdapter, VendorCredentials, VendorSiteSnapshot } from "./types";
// Generic mock helpers used in MOCK mode.
import { mockSitesFor, mockSnapshotFor } from "@/lib/mock/vendors";
// Error thrown by LIVE methods not yet wired to the real API.
import { NotImplemented } from "./not-implemented";

/**
 * Fortinet adapter (FortiGate-managed FortiAPs). LIVE mode uses the FortiGate
 * REST API with a bearer API token; FortiManager ADOMs can expose multiple
 * sites. A single FortiGate is treated as one site.
 */
export class FortinetAdapter implements VendorAdapter {
  // Machine id for this vendor.
  readonly vendor = "fortinet" as const;
  // Friendly name shown in the UI.
  readonly displayName = "Fortinet";
  // True when we have the credentials needed to reach the FortiGate API.
  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    // FortiGate needs a baseUrl plus a REST API token (carried in apiKey).
    this.live = Boolean(creds?.baseUrl && creds?.apiKey /* REST API token */);
  }

  async testConnection() {
    if (!this.live) return true; // MOCK: always "connected".
    // LIVE: GET {baseUrl}/api/v2/monitor/system/status  (Bearer token)
    // ^ A successful status response confirms the token works. Not built yet:
    throw new NotImplemented(this.displayName, "testConnection");
  }

  async listSites() {
    if (!this.live) return mockSitesFor(this.vendor); // MOCK: canned site list.
    // LIVE (FortiManager): GET /api/v2/cmdb/system/admin/... ADOMs/devices
    // LIVE (single FortiGate): one site = the device itself
    // ^ FortiManager can expose many sites; a lone FortiGate is just one. Not built yet:
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    // MOCK: build a fake snapshot for this site id.
    if (!this.live) return mockSnapshotFor(this.vendor, siteExternalId);
    // LIVE (FortiGate monitor API), normalize:
    //   GET /api/v2/monitor/wifi/managed_ap   -> access points (+ firmware)
    //   GET /api/v2/monitor/wifi/client       -> clients
    //   GET /api/v2/monitor/system/fortiguard / event log -> alerts
    // ^ Fetch each, normalize, and bundle into one snapshot. Not built yet:
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }
}
