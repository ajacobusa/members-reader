import type {
  VendorAdapter,
  VendorCredentials,
  VendorSiteSnapshot,
} from "./types";
import { arubaMockSnapshot, arubaMockSites } from "@/lib/mock/aruba";
import { NotImplemented } from "./not-implemented";

/**
 * Aruba Central adapter.
 *
 * Two modes:
 *  - MOCK (default): returns realistic fixture data so the whole MVP runs with
 *    no credentials. This is what powers the scaffold today.
 *  - LIVE: when `credentials` are provided, the *real* methods below talk to the
 *    Aruba Central REST API (token refresh + paginated pulls). Those calls are
 *    stubbed with the exact endpoints to wire and throw NotImplemented so the
 *    boundary is explicit. Fill them in when you have API access.
 *
 * Aruba Central exposes a REST API for monitoring (APs, clients, firmware) and
 * webhooks for alert events; LIVE mode pulls inventory here and a webhook route
 * (to add) ingests alerts in real time.
 */
export class ArubaCentralAdapter implements VendorAdapter {
  readonly vendor = "aruba_central" as const;
  readonly displayName = "Aruba Central";

  private readonly live: boolean;

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(creds?.baseUrl && creds?.clientId && creds?.clientSecret);
  }

  async testConnection(): Promise<boolean> {
    if (!this.live) return true; // mock is always "connected"
    return this.refreshToken().then(() => true);
  }

  async listSites(): Promise<{ externalId: string; name: string }[]> {
    if (!this.live) return arubaMockSites();
    // LIVE: GET {baseUrl}/central/v2/sites  (paginated; map id -> externalId)
    throw new NotImplemented(this.displayName, "listSites");
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return arubaMockSnapshot(siteExternalId);
    // LIVE: combine these monitoring endpoints, then normalize:
    //   GET /monitoring/v2/aps?site={id}              -> access points + firmware
    //   GET /monitoring/v1/clients?site={id}          -> clients (guest via SSID/role)
    //   GET /monitoring/v1/client/... / IoT inventory -> iot devices
    //   GET /central/v1/alerts?site={id}              -> alerts (or webhook ingest)
    throw new NotImplemented(this.displayName, `fetchSiteSnapshot(${siteExternalId})`);
  }

  /**
   * Aruba Central OAuth: exchange client credentials / refresh token for a
   * bearer access token. Stubbed until real credentials are available.
   */
  private async refreshToken(): Promise<string> {
    // LIVE: POST {baseUrl}/oauth2/token  (grant_type=refresh_token | client_credentials)
    throw new NotImplemented(this.displayName, "refreshToken");
  }
}
