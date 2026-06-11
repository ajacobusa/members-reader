// The normalized snapshot shape every vendor adapter must return (type only — no
// runtime cost). Using it here guarantees the mock matches the real sync output.
import type { VendorSiteSnapshot } from "@/integrations/types";

/**
 * Aruba Central fixture data — shaped exactly like a real normalized sync
 * result so the adapter's mock path and live path are interchangeable.
 */

// Lists the Aruba "sites" (properties) the integration can sync, as the live API would:
// each has an externalId (Aruba's own id) and a display name. Two demo sites here.
export function arubaMockSites(): { externalId: string; name: string }[] {
  return [
    { externalId: "site-aruba-001", name: "Harborview Hotel & Spa" },
    { externalId: "site-aruba-002", name: "Cedar Ridge Inn" },
  ];
}

// Returns the full normalized snapshot (APs, clients, IoT, alerts) for one Aruba site,
// matching what a real sync would produce — so the adapter can swap mock/live freely.
export function arubaMockSnapshot(siteExternalId: string): VendorSiteSnapshot {
  // Look up the site's friendly name by its external id; fall back if it's not one we know.
  const name =
    arubaMockSites().find((s) => s.externalId === siteExternalId)?.name ??
    "Unknown Site";

  // Build the snapshot. externalIds below are derived from the site id so they're unique
  // and stable per site (e.g. "site-aruba-001-ap-01").
  return {
    siteExternalId,
    siteName: name,
    // Two access points: one healthy lobby AP and one offline pool AP (with old firmware)
    // so the downstream score/firmware logic has something to react to.
    accessPoints: [
      {
        externalId: `${siteExternalId}-ap-01`,
        name: "Lobby-AP-01",
        model: "AP-635",
        serial: "CNABC1001",
        macAddress: "20:4c:03:1a:00:01",
        ipAddress: "10.10.1.11",
        status: "online",
        firmwareVersion: "10.4.1.0",
        firmwareRecommended: "10.6.0.2",
        clientCount: 42,
        uptimeSeconds: 1_900_000,
        lastSeen: "2026-06-10T14:55:00Z",
      },
      {
        externalId: `${siteExternalId}-ap-02`,
        name: "Pool-AP-04",
        model: "AP-505",
        serial: "CNABC1002",
        macAddress: "20:4c:03:1a:00:02",
        ipAddress: "10.10.1.12",
        status: "offline",
        firmwareVersion: "8.10.0.4",
        firmwareRecommended: "10.6.0.2",
        clientCount: 0,
        uptimeSeconds: 0,
        lastSeen: "2026-06-10T09:12:00Z",
      },
    ],
    // One sample guest client, linked to the lobby AP via accessPointExternalId.
    clients: [
      {
        externalId: `${siteExternalId}-cl-01`,
        hostname: "guest-iphone-77",
        macAddress: "aa:bb:cc:00:00:01",
        ssid: "Harborview-Guest",
        isGuest: true,
        signalDbm: -72,
        status: "online",
        connectionFailed: false,
        accessPointExternalId: `${siteExternalId}-ap-01`,
        lastSeen: "2026-06-10T14:54:00Z",
      },
    ],
    // One sample IoT device (a low-risk smart lock on the restricted IoT segment).
    iotDevices: [
      {
        externalId: `${siteExternalId}-iot-01`,
        name: "Smart Lock 3F-312",
        deviceType: "Door Lock",
        vendor: "Salto",
        macAddress: "dc:ef:00:11:22:01",
        vlan: 50,
        ssid: "Harborview-IoT",
        securityGroup: "iot-restricted",
        status: "online",
        riskLevel: "low",
        lastSeen: "2026-06-10T14:50:00Z",
      },
    ],
    // One critical alert matching the offline Pool-AP-04 above.
    alerts: [
      {
        externalId: `${siteExternalId}-al-01`,
        severity: "critical",
        title: "Access point Pool-AP-04 is down",
        description: "AP stopped responding to heartbeat 6h ago.",
        category: "ap_down",
        source: "aruba_central",
        raisedAt: "2026-06-10T09:12:00Z",
      },
    ],
  };
}
