import type { IntegrationVendorName } from "@/db/schema";
import type { VendorSiteSnapshot } from "@/integrations/types";

/**
 * Generic vendor fixture generator. Produces normalized snapshots shaped exactly
 * like a real sync result, flavored with each vendor's real hardware models and
 * firmware conventions — so the mock path and the eventual live path are
 * interchangeable for every manufacturer. Aruba has its own richer fixture in
 * mock/aruba.ts; the other five share this generator.
 */

interface VendorFlavor {
  /** Demo site name for this vendor. */
  site: string;
  apModels: [string, string];
  /** [installed, recommended] firmware — installed lags to exercise the tracker. */
  firmware: [string, string];
  ssidPrefix: string;
}

const FLAVORS: Partial<Record<IntegrationVendorName, VendorFlavor>> = {
  meraki: {
    site: "Sunset Bay Resort",
    apModels: ["MR46", "MR57"],
    firmware: ["29.7.1", "30.7"],
    ssidPrefix: "SunsetBay",
  },
  unifi: {
    site: "The Walnut Boutique Hotel",
    apModels: ["U6-Pro", "U7-Pro"],
    firmware: ["6.6.55", "7.0.66"],
    ssidPrefix: "Walnut",
  },
  ruckus: {
    site: "Grand Prairie Convention Hotel",
    apModels: ["R650", "R750"],
    firmware: ["6.1.1", "7.0.0"],
    ssidPrefix: "GrandPrairie",
  },
  fortinet: {
    site: "Ironside Business Center",
    apModels: ["FAP-431F", "FAP-231F"],
    firmware: ["7.2.1", "7.4.3"],
    ssidPrefix: "Ironside",
  },
  mist: {
    site: "Lakeshore Suites",
    apModels: ["AP43", "AP45"],
    firmware: ["0.12.x", "0.14.x"],
    ssidPrefix: "Lakeshore",
  },
};

export function flavorFor(vendor: IntegrationVendorName): VendorFlavor {
  const f = FLAVORS[vendor];
  if (!f) throw new Error(`No mock flavor for vendor "${vendor}".`);
  return f;
}

export function mockSitesFor(
  vendor: IntegrationVendorName
): { externalId: string; name: string }[] {
  return [{ externalId: `site-${vendor}-001`, name: flavorFor(vendor).site }];
}

export function mockSnapshotFor(
  vendor: IntegrationVendorName,
  siteExternalId: string
): VendorSiteSnapshot {
  const f = flavorFor(vendor);
  const [m1, m2] = f.apModels;
  const [fw, fwRec] = f.firmware;

  return {
    siteExternalId,
    siteName: f.site,
    accessPoints: [
      {
        externalId: `${siteExternalId}-ap-01`,
        name: "Lobby-AP-01",
        model: m1,
        macAddress: "00:11:22:00:00:01",
        ipAddress: "10.20.1.11",
        status: "online",
        firmwareVersion: fwRec,
        firmwareRecommended: fwRec,
        clientCount: 34,
        uptimeSeconds: 2_400_000,
        lastSeen: "2026-06-10T14:56:00Z",
      },
      {
        externalId: `${siteExternalId}-ap-02`,
        name: "Floor2-AP-05",
        model: m2,
        macAddress: "00:11:22:00:00:02",
        ipAddress: "10.20.1.12",
        status: "degraded",
        firmwareVersion: fw, // lags recommended → firmware tracker flags it
        firmwareRecommended: fwRec,
        clientCount: 12,
        uptimeSeconds: 600_000,
        lastSeen: "2026-06-10T14:40:00Z",
      },
    ],
    clients: [
      {
        externalId: `${siteExternalId}-cl-01`,
        hostname: "guest-device-21",
        macAddress: "aa:bb:cc:10:00:01",
        ssid: `${f.ssidPrefix}-Guest`,
        isGuest: true,
        signalDbm: -66,
        status: "online",
        connectionFailed: false,
        accessPointExternalId: `${siteExternalId}-ap-01`,
        lastSeen: "2026-06-10T14:55:00Z",
      },
    ],
    iotDevices: [
      {
        externalId: `${siteExternalId}-iot-01`,
        name: "Smart Thermostat 2F",
        deviceType: "HVAC",
        vendor: "Honeywell",
        macAddress: "dc:ef:10:22:00:01",
        vlan: 50,
        ssid: `${f.ssidPrefix}-IoT`,
        securityGroup: "iot-restricted",
        status: "online",
        riskLevel: "low",
        lastSeen: "2026-06-10T14:45:00Z",
      },
    ],
    alerts: [
      {
        externalId: `${siteExternalId}-al-01`,
        severity: "warning",
        title: `Firmware out of date on ${m2}`,
        description: `Floor2-AP-05 on ${fw}, recommended ${fwRec}.`,
        category: "firmware",
        source: vendor,
        raisedAt: "2026-06-09T20:00:00Z",
      },
    ],
  };
}
