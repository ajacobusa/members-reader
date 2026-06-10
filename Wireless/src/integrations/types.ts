import type { IntegrationVendorName, Severity, DeviceState, Risk } from "@/db/schema";

/**
 * Vendor adapter contract.
 *
 * Every manufacturer (Aruba Central first; Meraki, UniFi, Ruckus, Fortinet,
 * Mist later) implements this one interface. The pipeline pulls raw inventory
 * through these methods and normalizes it into our Postgres schema, so adding a
 * vendor never touches the dashboard, the health scoring, or the DB.
 *
 * Methods return *normalized* records keyed by the vendor's external id. The
 * sync job maps these onto rows in access_points / clients / alerts / etc.
 */

export interface VendorCredentials {
  baseUrl?: string;
  clientId?: string;
  clientSecret?: string;
  /** Aruba customer id, Meraki organization id, or Mist org id, per vendor. */
  customerId?: string;
  /** OAuth refresh token, when the vendor uses one. */
  refreshToken?: string;
  /** API key / token (Meraki, UniFi Site Manager, Fortinet, Mist, RUCKUS One). */
  apiKey?: string;
  /** Controller login (self-hosted UniFi, RUCKUS SmartZone). */
  username?: string;
  password?: string;
  [key: string]: string | undefined;
}

export interface NormalizedAccessPoint {
  externalId: string;
  name: string;
  model?: string;
  serial?: string;
  macAddress?: string;
  ipAddress?: string;
  status: DeviceState;
  firmwareVersion?: string;
  firmwareRecommended?: string;
  clientCount: number;
  uptimeSeconds: number;
  lastSeen?: string; // ISO8601
}

export interface NormalizedClient {
  externalId: string;
  hostname?: string;
  macAddress?: string;
  ssid?: string;
  isGuest: boolean;
  signalDbm?: number;
  status: DeviceState;
  connectionFailed: boolean;
  accessPointExternalId?: string;
  lastSeen?: string;
}

export interface NormalizedIotDevice {
  externalId: string;
  name: string;
  deviceType?: string;
  vendor?: string;
  macAddress?: string;
  vlan?: number;
  ssid?: string;
  securityGroup?: string;
  status: DeviceState;
  riskLevel: Risk;
  lastSeen?: string;
}

export interface NormalizedAlert {
  externalId: string;
  severity: Severity;
  title: string;
  description?: string;
  category?: string;
  source?: string;
  raisedAt?: string;
}

export interface VendorSiteSnapshot {
  /** The vendor's identifier for this site/property. */
  siteExternalId: string;
  siteName: string;
  accessPoints: NormalizedAccessPoint[];
  clients: NormalizedClient[];
  iotDevices: NormalizedIotDevice[];
  alerts: NormalizedAlert[];
}

export interface VendorAdapter {
  readonly vendor: IntegrationVendorName;
  /** Human label, e.g. "Aruba Central". */
  readonly displayName: string;

  /** Verify credentials / token. Returns true when the connection is live. */
  testConnection(): Promise<boolean>;

  /** List the sites (properties) visible to these credentials. */
  listSites(): Promise<{ externalId: string; name: string }[]>;

  /** Pull a full normalized snapshot for one site. */
  fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot>;
}
