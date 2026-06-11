// Pull in the shared "enum-like" string types from our database schema so the
// adapter layer and the DB always agree on the exact set of allowed values.
//   IntegrationVendorName - which vendor this is, e.g. "aruba_central" | "meraki"
//   Severity              - alert severity level, e.g. "critical" | "warning"
//   DeviceState           - online/offline status of a device, e.g. "online"
//   Risk                  - risk rating for an IoT device, e.g. "low" | "high"
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

// The set of login details we might need to talk to a vendor's API. Every field
// is optional (`?`) because each vendor uses a different subset — Aruba needs
// OAuth client id/secret, Meraki needs an API key, self-hosted UniFi needs a
// username/password, and so on. We carry one flexible bag and each adapter reads
// only the fields it cares about.
export interface VendorCredentials {
  // Base URL of the vendor's API host, e.g. "https://apigw.central.arubanetworks.com".
  baseUrl?: string;
  // OAuth client identifier (the "app" id) for vendors that use OAuth2.
  clientId?: string;
  // OAuth client secret (the matching password for the clientId). Keep private.
  clientSecret?: string;
  /** Aruba customer id, Meraki organization id, or Mist org id, per vendor. */
  // The "account/tenant" id that scopes which devices we can see. Each vendor
  // names it differently, but it plays the same role.
  customerId?: string;
  /** OAuth refresh token, when the vendor uses one. */
  // Long-lived token we trade in for a short-lived access token (Aruba OAuth).
  refreshToken?: string;
  /** API key / token (Meraki, UniFi Site Manager, Fortinet, Mist, RUCKUS One). */
  // A single secret string that authenticates every request via a header.
  apiKey?: string;
  /** Controller login (self-hosted UniFi, RUCKUS SmartZone). */
  // Classic username/password pair for on-premise controllers that log in with
  // a session cookie or ticket instead of a token.
  username?: string;
  password?: string;
  // Index signature: allow any other string-keyed field so a vendor can stash
  // extra credential bits without us editing this interface. Values are either a
  // string or undefined (matching the optional fields above).
  [key: string]: string | undefined;
}

// One Wi-Fi access point (AP) after we've translated it out of vendor-specific
// shapes into the single, consistent shape the rest of the app understands.
export interface NormalizedAccessPoint {
  // The vendor's own unique id for this AP; we use it to match/update DB rows.
  externalId: string;
  // Human-friendly AP name as configured in the vendor dashboard.
  name: string;
  // Hardware model string, e.g. "AP-515". Optional — not all vendors report it.
  model?: string;
  // Manufacturer serial number, useful for support/RMA. Optional.
  serial?: string;
  // The AP's MAC (hardware) address. Optional.
  macAddress?: string;
  // The AP's current IP address on the network. Optional.
  ipAddress?: string;
  // Whether the device is online/offline, using our shared DeviceState type.
  status: DeviceState;
  // Firmware currently running on the AP. Optional.
  firmwareVersion?: string;
  // Firmware the vendor recommends; compare with the above to flag updates.
  firmwareRecommended?: string;
  // How many clients are connected to this AP right now (always reported).
  clientCount: number;
  // How long the AP has been up, in seconds (always reported).
  uptimeSeconds: number;
  lastSeen?: string; // ISO8601
  // ^ Timestamp the AP was last seen by the controller, as an ISO8601 string.
}

// One connected client device (laptop, phone, etc.) in normalized form.
export interface NormalizedClient {
  // The vendor's unique id for this client session/device.
  externalId: string;
  // Device hostname if known, e.g. "Johns-iPhone". Optional.
  hostname?: string;
  // Client's MAC (hardware) address. Optional.
  macAddress?: string;
  // The Wi-Fi network name (SSID) the client is joined to. Optional.
  ssid?: string;
  // True if this is a guest-network client (vs. a trusted/internal one).
  isGuest: boolean;
  // Signal strength in dBm (e.g. -65). Closer to 0 is stronger. Optional.
  signalDbm?: number;
  // Online/offline state, using the shared DeviceState type.
  status: DeviceState;
  // True if the client's last connection attempt failed (auth/DHCP/etc.).
  connectionFailed: boolean;
  // externalId of the AP this client is associated with, linking the two.
  accessPointExternalId?: string;
  // ISO8601 timestamp the client was last seen. Optional.
  lastSeen?: string;
}

// One IoT device (camera, sensor, smart TV, etc.) in normalized form. IoT
// devices get extra security-oriented fields because they're often the weakest
// link on a network.
export interface NormalizedIotDevice {
  // The vendor's unique id for this IoT device.
  externalId: string;
  // Human-friendly device name.
  name: string;
  // Category of device, e.g. "camera" or "thermostat". Optional.
  deviceType?: string;
  // The device manufacturer, if the vendor can identify it. Optional.
  vendor?: string;
  // Device MAC (hardware) address. Optional.
  macAddress?: string;
  // VLAN number the device sits on, for network segmentation. Optional.
  vlan?: number;
  // SSID the device connects through, if wireless. Optional.
  ssid?: string;
  // Security/policy group the device is assigned to. Optional.
  securityGroup?: string;
  // Online/offline state, using the shared DeviceState type.
  status: DeviceState;
  // Risk rating (low/medium/high) using the shared Risk type — drives alerts.
  riskLevel: Risk;
  // ISO8601 timestamp the device was last seen. Optional.
  lastSeen?: string;
}

// One alert/alarm event in normalized form (e.g. "AP offline", "rogue SSID").
export interface NormalizedAlert {
  // The vendor's unique id for this alert, so we don't insert duplicates.
  externalId: string;
  // How serious the alert is, using the shared Severity type.
  severity: Severity;
  // Short headline describing the alert.
  title: string;
  // Longer human-readable explanation. Optional.
  description?: string;
  // Grouping/category for filtering, e.g. "connectivity". Optional.
  category?: string;
  // Where the alert came from, e.g. the AP name or subsystem. Optional.
  source?: string;
  // ISO8601 timestamp the alert was first raised. Optional.
  raisedAt?: string;
}

// A complete, point-in-time picture of ONE site (property/building): all of its
// APs, clients, IoT devices, and alerts bundled together. This is the payload a
// single sync pulls and the pipeline writes to the database.
export interface VendorSiteSnapshot {
  /** The vendor's identifier for this site/property. */
  siteExternalId: string;
  // Human-friendly site name shown in the dashboard.
  siteName: string;
  // All access points at this site (normalized).
  accessPoints: NormalizedAccessPoint[];
  // All connected clients at this site (normalized).
  clients: NormalizedClient[];
  // All IoT devices at this site (normalized).
  iotDevices: NormalizedIotDevice[];
  // All open alerts for this site (normalized).
  alerts: NormalizedAlert[];
}

// The contract EVERY vendor adapter must fulfill. As long as a class provides
// these three methods (plus the two identity fields), the rest of the platform
// can drive any manufacturer the same way without knowing vendor specifics.
export interface VendorAdapter {
  // Machine-readable vendor id; `readonly` means it can't change after creation.
  readonly vendor: IntegrationVendorName;
  /** Human label, e.g. "Aruba Central". */
  readonly displayName: string;

  /** Verify credentials / token. Returns true when the connection is live. */
  // Async because it may hit the network; resolves to true if creds work.
  testConnection(): Promise<boolean>;

  /** List the sites (properties) visible to these credentials. */
  // Returns a lightweight list of {externalId, name} the user can pick from.
  listSites(): Promise<{ externalId: string; name: string }[]>;

  /** Pull a full normalized snapshot for one site. */
  // Given one site id, fetch and normalize everything into a VendorSiteSnapshot.
  fetchSiteSnapshot(siteExternalId: string): Promise<VendorSiteSnapshot>;
}
