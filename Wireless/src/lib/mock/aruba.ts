import type { VendorSiteSnapshot } from "@/integrations/types";

/**
 * Aruba Central fixture data — shaped exactly like a real normalized sync
 * result so the adapter's mock path and live path are interchangeable.
 */

export function arubaMockSites(): { externalId: string; name: string }[] {
  return [
    { externalId: "site-aruba-001", name: "Harborview Hotel & Spa" },
    { externalId: "site-aruba-002", name: "Cedar Ridge Inn" },
  ];
}

export function arubaMockSnapshot(siteExternalId: string): VendorSiteSnapshot {
  const name =
    arubaMockSites().find((s) => s.externalId === siteExternalId)?.name ??
    "Unknown Site";

  return {
    siteExternalId,
    siteName: name,
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
