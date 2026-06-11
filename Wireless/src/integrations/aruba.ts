// Shared contract + data shapes this adapter conforms to.
import type {
  VendorAdapter,
  VendorCredentials,
  VendorSiteSnapshot,
  NormalizedAccessPoint,
  NormalizedClient,
  NormalizedAlert,
} from "./types";
// Fixture data served in MOCK mode (no credentials).
import { arubaMockSnapshot, arubaMockSites } from "@/lib/mock/aruba";

/**
 * Aruba Central adapter.
 *
 * Two modes, chosen by whether credentials are present:
 *  - MOCK (default): returns realistic fixture data so the whole platform runs
 *    with no credentials.
 *  - LIVE: talks to the Aruba Central REST API — OAuth2 token handling plus
 *    paginated pulls of sites, APs, and clients, normalized into our shapes.
 *
 * LIVE credentials (stored encrypted on the integration row):
 *   baseUrl      e.g. https://apigw-uswest4.central.arubanetworks.com
 *   clientId     OAuth client id from Central → API Gateway
 *   clientSecret OAuth client secret
 *   refreshToken OAuth refresh token (preferred grant), OR omit to attempt
 *                client_credentials (supported on newer Central deployments)
 *   customerId   Central customer id (sent on token refresh)
 *
 * NOTE: response field mapping below follows Aruba's published monitoring API
 * docs; a first run against a real tenant may need small field tweaks (kept
 * defensive with fallbacks so unexpected shapes degrade, not crash).
 */
export class ArubaCentralAdapter implements VendorAdapter {
  readonly vendor = "aruba_central" as const;
  readonly displayName = "Aruba Central";

  // True when enough credentials exist to attempt real API calls.
  private readonly live: boolean;
  // Cached bearer token for this adapter instance (Aruba tokens last ~2h).
  private token: string | null = null;
  // Maps site externalId -> site name; monitoring endpoints filter by NAME.
  private siteNames = new Map<string, string>();

  constructor(private readonly creds?: VendorCredentials) {
    this.live = Boolean(
      creds?.baseUrl && creds?.clientId && creds?.clientSecret
    );
  }

  async testConnection(): Promise<boolean> {
    if (!this.live) return true; // mock is always "connected"
    await this.getToken();
    return true;
  }

  async listSites(): Promise<{ externalId: string; name: string }[]> {
    if (!this.live) return arubaMockSites();
    // LIVE: GET /central/v2/sites — paginated list of sites for this customer.
    const sites: { externalId: string; name: string }[] = [];
    let offset = 0;
    const limit = 100;
    for (;;) {
      const page = await this.get<{
        sites?: { site_id?: number | string; site_name?: string }[];
        total?: number;
      }>(`/central/v2/sites?calculate_total=true&offset=${offset}&limit=${limit}`);
      for (const s of page.sites ?? []) {
        const id = String(s.site_id ?? "");
        const name = s.site_name ?? id;
        if (id) {
          sites.push({ externalId: id, name });
          this.siteNames.set(id, name);
        }
      }
      offset += limit;
      if (!page.sites?.length || sites.length >= (page.total ?? sites.length)) break;
    }
    return sites;
  }

  async fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot> {
    if (!this.live) return arubaMockSnapshot(siteExternalId);

    // Monitoring endpoints filter by site NAME — resolve it (refresh the site
    // list once if this id hasn't been seen by this instance yet).
    if (!this.siteNames.has(siteExternalId)) await this.listSites();
    const siteName = this.siteNames.get(siteExternalId) ?? siteExternalId;
    const site = encodeURIComponent(siteName);

    // Pull APs, clients, and alerts in parallel — each defensive and paginated
    // where the API supports it.
    const [accessPoints, clients, alerts] = await Promise.all([
      this.fetchAps(site),
      this.fetchClients(site),
      this.fetchAlerts(site),
    ]);

    return {
      siteExternalId,
      siteName,
      accessPoints,
      clients,
      // Aruba has no first-class IoT inventory endpoint; IoT devices are
      // classified from client fingerprints in a later enrichment pass.
      iotDevices: [],
      alerts,
    };
  }

  // ---- LIVE pulls ----------------------------------------------------------

  private async fetchAps(site: string): Promise<NormalizedAccessPoint[]> {
    // GET /monitoring/v2/aps — AP inventory incl. status/firmware/clients.
    const data = await this.get<{ aps?: Record<string, unknown>[] }>(
      `/monitoring/v2/aps?site=${site}&limit=1000&offset=0&calculate_client_count=true`
    );
    return (data.aps ?? []).map((ap) => ({
      externalId: str(ap.serial) || str(ap.macaddr) || str(ap.name),
      name: str(ap.name) || str(ap.serial) || "Unknown AP",
      model: str(ap.model) || undefined,
      serial: str(ap.serial) || undefined,
      macAddress: str(ap.macaddr) || undefined,
      ipAddress: str(ap.ip_address) || undefined,
      // Central reports "Up"/"Down"; anything else maps to degraded.
      status:
        str(ap.status).toLowerCase() === "up"
          ? "online"
          : str(ap.status).toLowerCase() === "down"
            ? "offline"
            : "degraded",
      firmwareVersion: str(ap.firmware_version) || undefined,
      firmwareRecommended: undefined, // filled by the firmware compliance API later
      clientCount: num(ap.client_count),
      uptimeSeconds: num(ap.uptime),
      lastSeen: new Date().toISOString(),
    }));
  }

  private async fetchClients(site: string): Promise<NormalizedClient[]> {
    // GET /monitoring/v2/clients — unified wireless client list for the site.
    const data = await this.get<{ clients?: Record<string, unknown>[] }>(
      `/monitoring/v2/clients?site=${site}&client_type=WIRELESS&limit=1000&offset=0`
    );
    return (data.clients ?? []).map((c) => ({
      externalId: str(c.macaddr) || str(c.name),
      hostname: str(c.hostname) || str(c.name) || undefined,
      macAddress: str(c.macaddr) || undefined,
      ssid: str(c.network) || undefined,
      // Heuristic: SSIDs containing "guest" count as guest WiFi (refine with
      // user-role data when available on the tenant).
      isGuest: str(c.network).toLowerCase().includes("guest"),
      signalDbm: c.signal_db != null ? -Math.abs(num(c.signal_db)) : undefined,
      status: str(c.health).toLowerCase() === "poor" ? "degraded" : "online",
      connectionFailed: false, // populated from auth-failure events later
      accessPointExternalId: str(c.associated_device) || undefined,
      lastSeen: new Date().toISOString(),
    }));
  }

  private async fetchAlerts(site: string): Promise<NormalizedAlert[]> {
    // GET /monitoring/v2/alerts — open alerts; falls back to empty on tenants
    // where alerting rides the webhook channel instead.
    try {
      const data = await this.get<{ alerts?: Record<string, unknown>[] }>(
        `/monitoring/v2/alerts?site=${site}&limit=100&offset=0`
      );
      return (data.alerts ?? []).map((a) => ({
        externalId: str(a.id) || `${str(a.type)}-${str(a.timestamp)}`,
        severity:
          str(a.severity).toLowerCase() === "critical" ||
          str(a.severity).toLowerCase() === "major"
            ? "critical"
            : str(a.severity).toLowerCase() === "minor" ||
                str(a.severity).toLowerCase() === "warning"
              ? "warning"
              : "info",
        title: str(a.description) || str(a.type) || "Aruba alert",
        description: str(a.details) || undefined,
        category: str(a.type) || undefined,
        source: "aruba_central",
        raisedAt: a.timestamp ? new Date(num(a.timestamp) * 1000).toISOString() : undefined,
      }));
    } catch {
      // Alert pull is non-fatal: inventory sync still succeeds without it.
      return [];
    }
  }

  // ---- OAuth + HTTP plumbing ----------------------------------------------

  /** Get (and cache) a bearer token via refresh_token or client_credentials. */
  private async getToken(): Promise<string> {
    if (this.token) return this.token;
    const { baseUrl, clientId, clientSecret, refreshToken, customerId } =
      this.creds!;

    // Preferred: refresh_token grant (standard for Aruba Central API gateways).
    // Fallback: client_credentials (available on newer deployments).
    const params = refreshToken
      ? new URLSearchParams({
          client_id: clientId!,
          client_secret: clientSecret!,
          grant_type: "refresh_token",
          refresh_token: refreshToken,
        })
      : new URLSearchParams({
          client_id: clientId!,
          client_secret: clientSecret!,
          grant_type: "client_credentials",
          ...(customerId ? { customer_id: customerId } : {}),
        });

    const res = await fetch(`${baseUrl}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params.toString(),
    });
    if (!res.ok) {
      throw new Error(
        `Aruba OAuth failed: ${res.status} ${res.statusText} — ${await safeText(res)}`
      );
    }
    const json = (await res.json()) as { access_token?: string };
    if (!json.access_token) throw new Error("Aruba OAuth: no access_token in response");
    this.token = json.access_token;
    return this.token;
  }

  /** Authenticated GET against the Central API gateway with clear errors. */
  private async get<T>(path: string): Promise<T> {
    const token = await this.getToken();
    const res = await fetch(`${this.creds!.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      throw new Error(
        `Aruba API ${path} failed: ${res.status} ${res.statusText} — ${await safeText(res)}`
      );
    }
    return (await res.json()) as T;
  }
}

// Tolerant field coercion: vendor payloads vary, so never throw on shape.
function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}
function num(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}
async function safeText(res: Response): Promise<string> {
  try {
    return (await res.text()).slice(0, 300);
  } catch {
    return "<no body>";
  }
}
