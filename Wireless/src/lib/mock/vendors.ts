// The union of valid vendor names (e.g. "meraki" | "unifi" | …) from the schema — used
// to key the flavor table and constrain function arguments. Type-only import.
import type { IntegrationVendorName } from "@/db/schema";
// The normalized snapshot shape every adapter returns; we produce it below.
import type { VendorSiteSnapshot } from "@/integrations/types";

/**
 * Generic vendor fixture generator. Produces normalized snapshots shaped exactly
 * like a real sync result, flavored with each vendor's real hardware models and
 * firmware conventions — so the mock path and the eventual live path are
 * interchangeable for every manufacturer. Aruba has its own richer fixture in
 * mock/aruba.ts; the other five share this generator.
 */

// The per-vendor "flavor": the few real-world details that make each generated snapshot
// look authentic to its manufacturer. The [string, string] tuple types mean exactly two
// entries (a pair), used for the two AP models and the installed/recommended firmware.
interface VendorFlavor {
  /** Demo site name for this vendor. */
  site: string;
  apModels: [string, string];
  /** [installed, recommended] firmware — installed lags to exercise the tracker. */
  firmware: [string, string];
  ssidPrefix: string;
}

// Lookup table of flavors keyed by vendor name. `Partial<Record<...>>` means not every
// vendor must be present (Aruba is intentionally absent — it has its own richer fixture).
const FLAVORS: Partial<Record<IntegrationVendorName, VendorFlavor>> = {
  // Cisco Meraki — MR-series APs, dotted firmware versions.
  meraki: {
    site: "Sunset Bay Resort",
    apModels: ["MR46", "MR57"],
    firmware: ["29.7.1", "30.7"],
    ssidPrefix: "SunsetBay",
  },
  // Ubiquiti UniFi — U6/U7 APs.
  unifi: {
    site: "The Walnut Boutique Hotel",
    apModels: ["U6-Pro", "U7-Pro"],
    firmware: ["6.6.55", "7.0.66"],
    ssidPrefix: "Walnut",
  },
  // RUCKUS — R-series APs.
  ruckus: {
    site: "Grand Prairie Convention Hotel",
    apModels: ["R650", "R750"],
    firmware: ["6.1.1", "7.0.0"],
    ssidPrefix: "GrandPrairie",
  },
  // Fortinet — FAP (FortiAP) models.
  fortinet: {
    site: "Ironside Business Center",
    apModels: ["FAP-431F", "FAP-231F"],
    firmware: ["7.2.1", "7.4.3"],
    ssidPrefix: "Ironside",
  },
  // Juniper Mist — AP4x models, "0.x" style firmware.
  mist: {
    site: "Lakeshore Suites",
    apModels: ["AP43", "AP45"],
    firmware: ["0.12.x", "0.14.x"],
    ssidPrefix: "Lakeshore",
  },
};

// Safely fetch a vendor's flavor. Because FLAVORS is Partial, the lookup may be
// undefined — so we throw a clear error rather than letting code silently break later.
export function flavorFor(vendor: IntegrationVendorName): VendorFlavor {
  const f = FLAVORS[vendor];
  if (!f) throw new Error(`No mock flavor for vendor "${vendor}".`);
  return f;
}

// Lists the demo site(s) for a vendor — mirrors arubaMockSites() but generated. Each
// vendor has a single site, with a deterministic externalId like "site-meraki-001".
export function mockSitesFor(
  vendor: IntegrationVendorName
): { externalId: string; name: string }[] {
  return [{ externalId: `site-${vendor}-001`, name: flavorFor(vendor).site }];
}

// Generates a full normalized snapshot for any of the five supported vendors, using
// that vendor's flavor to fill in realistic models, firmware, and SSIDs.
export function mockSnapshotFor(
  vendor: IntegrationVendorName,
  siteExternalId: string
): VendorSiteSnapshot {
  // Grab the vendor's flavor and destructure its two AP models and firmware pair.
  const f = flavorFor(vendor);
  const [m1, m2] = f.apModels; // m1 = lobby/online model, m2 = the lagging model
  const [fw, fwRec] = f.firmware; // fw = installed (older), fwRec = recommended (newer)

  return {
    siteExternalId,
    siteName: f.site,
    // Two APs: an online lobby AP already on the recommended firmware, and a degraded
    // floor AP deliberately left on the older firmware to exercise the lag tracker.
    accessPoints: [
      {
        externalId: `${siteExternalId}-ap-01`,
        name: "Lobby-AP-01",
        model: m1,
        macAddress: "00:11:22:00:00:01",
        ipAddress: "10.20.1.11",
        status: "online",
        firmwareVersion: fwRec, // already on recommended → not flagged
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
    // One guest client on the vendor's "<Prefix>-Guest" SSID, linked to the lobby AP.
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
    // One low-risk IoT device (a thermostat) on the restricted IoT segment.
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
    // One firmware warning that matches the lagging AP above; its text is built from the
    // model and firmware values so the message stays consistent with the data.
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
