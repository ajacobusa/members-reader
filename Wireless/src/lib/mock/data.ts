import type {
  Company,
  Property,
  Integration,
  AccessPoint,
  Client,
  IotDevice,
  Alert,
  Incident,
  Vendor,
  Project,
} from "@/db/schema";

/**
 * Canonical in-memory dataset. Typed against the Drizzle-inferred schema types,
 * so it is structurally identical to what the database returns. The queries
 * layer (lib/queries.ts) reads from here today; swapping to Postgres later means
 * changing only that file.
 */

const d = (iso: string) => new Date(iso);

// Stable ids so links work across page loads.
export const ID = {
  company: "00000000-0000-0000-0000-000000000001",
  p1: "00000000-0000-0000-0000-0000000000a1", // Harborview      (Aruba)
  p2: "00000000-0000-0000-0000-0000000000a2", // Cedar Ridge      (Aruba)
  p3: "00000000-0000-0000-0000-0000000000a3", // Metro Suites      (Aruba)
  p4: "00000000-0000-0000-0000-0000000000a4", // Sunset Bay        (Meraki)
  p5: "00000000-0000-0000-0000-0000000000a5", // Walnut Boutique   (UniFi)
  p6: "00000000-0000-0000-0000-0000000000a6", // Grand Prairie     (RUCKUS)
  p7: "00000000-0000-0000-0000-0000000000a7", // Ironside          (Fortinet)
  p8: "00000000-0000-0000-0000-0000000000a8", // Lakeshore         (Mist)
  arubaIntegration: "00000000-0000-0000-0000-0000000000b1",
} as const;

export const companies: Company[] = [
  {
    id: ID.company,
    name: "Coastline Hospitality Group",
    slug: "coastline",
    createdAt: d("2026-01-04T00:00:00Z"),
  },
];

export const properties: Property[] = [
  {
    id: ID.p1,
    companyId: ID.company,
    name: "Harborview Hotel & Spa",
    address: "1 Harbor Way",
    city: "Portland",
    region: "ME",
    timezone: "America/New_York",
    healthScore: 62,
    managedBy: "aruba_central",
    createdAt: d("2026-01-10T00:00:00Z"),
  },
  {
    id: ID.p2,
    companyId: ID.company,
    name: "Cedar Ridge Inn",
    address: "88 Cedar Ridge Rd",
    city: "Asheville",
    region: "NC",
    timezone: "America/New_York",
    healthScore: 88,
    managedBy: "aruba_central",
    createdAt: d("2026-01-12T00:00:00Z"),
  },
  {
    id: ID.p3,
    companyId: ID.company,
    name: "Metro Business Suites",
    address: "400 Market St",
    city: "Austin",
    region: "TX",
    timezone: "America/Chicago",
    healthScore: 94,
    managedBy: "aruba_central",
    createdAt: d("2026-02-01T00:00:00Z"),
  },
  prop(ID.p4, "Sunset Bay Resort", "12 Ocean Dr", "Miami", "FL", "America/New_York", "meraki"),
  prop(ID.p5, "The Walnut Boutique Hotel", "55 Walnut St", "Denver", "CO", "America/Denver", "unifi"),
  prop(ID.p6, "Grand Prairie Convention Hotel", "900 Expo Blvd", "Dallas", "TX", "America/Chicago", "ruckus"),
  prop(ID.p7, "Ironside Business Center", "70 Wacker Dr", "Chicago", "IL", "America/Chicago", "fortinet"),
  prop(ID.p8, "Lakeshore Suites", "230 Lakeshore Ave", "Seattle", "WA", "America/Los_Angeles", "mist"),
];

function prop(
  id: string,
  name: string,
  address: string,
  city: string,
  region: string,
  timezone: string,
  managedBy: Property["managedBy"]
): Property {
  return {
    id,
    companyId: ID.company,
    name,
    address,
    city,
    region,
    timezone,
    healthScore: 100, // illustrative; the UI recomputes live from devices/alerts
    managedBy,
    createdAt: d("2026-02-15T00:00:00Z"),
  };
}

export const integrations: Integration[] = [
  {
    id: ID.arubaIntegration,
    companyId: ID.company,
    vendor: "aruba_central",
    label: "Aruba Central (Production)",
    status: "connected",
    baseUrl: "https://apigw-uswest.central.arubanetworks.com",
    credentials: null,
    lastSyncedAt: d("2026-06-10T14:55:00Z"),
    lastError: null,
    createdAt: d("2026-01-10T00:00:00Z"),
  },
  integration("meraki", "Cisco Meraki Dashboard", "https://api.meraki.com/api/v1"),
  integration("unifi", "UniFi Site Manager", "https://api.ui.com"),
  integration("ruckus", "RUCKUS SmartZone", "https://smartzone.example.com:8443"),
  integration("fortinet", "Fortinet FortiGate", "https://fortigate.example.com"),
  integration("mist", "Juniper Mist Cloud", "https://api.mist.com"),
];

function integration(
  vendor: Integration["vendor"],
  label: string,
  baseUrl: string
): Integration {
  return {
    id: crypto.randomUUID(),
    companyId: ID.company,
    vendor,
    label,
    status: "connected",
    baseUrl,
    credentials: null,
    lastSyncedAt: d("2026-06-10T14:50:00Z"),
    lastError: null,
    createdAt: d("2026-02-15T00:00:00Z"),
  };
}

// --- Access points -----------------------------------------------------------

export const accessPoints: AccessPoint[] = [
  ap(ID.p1, "Lobby-AP-01", "AP-635", "online", "10.4.1.0", "10.6.0.2", 42, 1_900_000, "2026-06-10T14:55:00Z"),
  ap(ID.p1, "Pool-AP-04", "AP-505", "offline", "8.10.0.4", "10.6.0.2", 0, 0, "2026-06-10T09:12:00Z"),
  ap(ID.p1, "Conf-AP-07", "AP-635", "degraded", "10.5.0.1", "10.6.0.2", 18, 540_000, "2026-06-10T14:50:00Z"),
  ap(ID.p2, "Lobby-AP-01", "AP-505", "online", "10.6.0.2", "10.6.0.2", 21, 3_200_000, "2026-06-10T14:58:00Z"),
  ap(ID.p2, "Wing-A-AP-03", "AP-505", "online", "10.6.0.2", "10.6.0.2", 15, 3_100_000, "2026-06-10T14:57:00Z"),
  ap(ID.p3, "Floor3-AP-12", "AP-655", "online", "10.6.0.2", "10.6.0.2", 30, 5_000_000, "2026-06-10T14:59:00Z"),
  // Meraki — Sunset Bay
  ap(ID.p4, "Lobby-AP-01", "MR46", "online", "30.7", "30.7", 34, 2_400_000, "2026-06-10T14:56:00Z"),
  ap(ID.p4, "Pool-AP-03", "MR57", "degraded", "29.7.1", "30.7", 12, 600_000, "2026-06-10T14:40:00Z"),
  // UniFi — Walnut Boutique
  ap(ID.p5, "Lobby-AP-01", "U6-Pro", "online", "7.0.66", "7.0.66", 19, 1_800_000, "2026-06-10T14:57:00Z"),
  ap(ID.p5, "WingB-AP-02", "U7-Pro", "offline", "6.6.55", "7.0.66", 0, 0, "2026-06-10T07:30:00Z"),
  // RUCKUS — Grand Prairie
  ap(ID.p6, "Hall-AP-01", "R650", "online", "7.0.0", "7.0.0", 88, 4_200_000, "2026-06-10T14:58:00Z"),
  ap(ID.p6, "Hall-AP-02", "R750", "online", "7.0.0", "7.0.0", 64, 4_100_000, "2026-06-10T14:58:00Z"),
  // Fortinet — Ironside
  ap(ID.p7, "Floor1-AP-01", "FAP-431F", "online", "7.4.3", "7.4.3", 41, 3_600_000, "2026-06-10T14:59:00Z"),
  ap(ID.p7, "Floor4-AP-02", "FAP-231F", "degraded", "7.2.1", "7.4.3", 9, 300_000, "2026-06-10T14:35:00Z"),
  // Mist — Lakeshore
  ap(ID.p8, "Lobby-AP-01", "AP43", "online", "0.14.x", "0.14.x", 27, 5_200_000, "2026-06-10T14:59:00Z"),
  ap(ID.p8, "Suite-AP-09", "AP45", "online", "0.14.x", "0.14.x", 16, 5_000_000, "2026-06-10T14:59:00Z"),
];

function ap(
  propertyId: string,
  name: string,
  model: string,
  status: AccessPoint["status"],
  fw: string,
  fwRec: string,
  clientCount: number,
  uptime: number,
  lastSeen: string
): AccessPoint {
  return {
    id: crypto.randomUUID(),
    propertyId,
    name,
    model,
    serial: null,
    macAddress: null,
    ipAddress: null,
    status,
    firmwareVersion: fw,
    firmwareRecommended: fwRec,
    clientCount,
    uptimeSeconds: uptime,
    lastSeen: d(lastSeen),
    externalId: null,
    createdAt: d("2026-01-10T00:00:00Z"),
  };
}

// --- Clients -----------------------------------------------------------------

export const clients: Client[] = [
  client(ID.p1, "guest-iphone-77", "Harborview-Guest", true, -72, "online", false),
  client(ID.p1, "guest-laptop-12", "Harborview-Guest", true, -81, "degraded", true),
  client(ID.p1, "pos-terminal-3", "Harborview-Staff", false, -55, "online", false),
  client(ID.p2, "guest-pixel-44", "Cedar-Guest", true, -60, "online", false),
  client(ID.p3, "exec-macbook-1", "Metro-Corp", false, -48, "online", false),
  client(ID.p4, "guest-ipad-31", "SunsetBay-Guest", true, -64, "online", false),
  client(ID.p5, "guest-galaxy-08", "Walnut-Guest", true, -83, "degraded", true),
  client(ID.p6, "conf-laptop-22", "GrandPrairie-Corp", false, -52, "online", false),
  client(ID.p7, "staff-thinkpad-5", "Ironside-Staff", false, -57, "online", false),
  client(ID.p8, "guest-iphone-90", "Lakeshore-Guest", true, -61, "online", false),
];

function client(
  propertyId: string,
  hostname: string,
  ssid: string,
  isGuest: boolean,
  signal: number,
  status: Client["status"],
  failed: boolean
): Client {
  return {
    id: crypto.randomUUID(),
    propertyId,
    accessPointId: null,
    hostname,
    macAddress: null,
    ssid,
    isGuest: isGuest ? 1 : 0,
    signalDbm: signal,
    status,
    connectionFailed: failed ? 1 : 0,
    lastSeen: d("2026-06-10T14:54:00Z"),
    createdAt: d("2026-06-01T00:00:00Z"),
  };
}

// --- IoT devices -------------------------------------------------------------

export const iotDevices: IotDevice[] = [
  iot(ID.p1, "Smart Lock 3F-312", "Door Lock", "Salto", 50, "iot-restricted", "online", "low"),
  iot(ID.p1, "Thermostat-Lobby", "HVAC", "Honeywell", 50, "iot-restricted", "online", "medium"),
  iot(ID.p1, "IP Camera East-Hall", "Camera", "Axis", 60, "iot-cameras", "offline", "high"),
  iot(ID.p2, "Mini-bar Sensor 204", "Sensor", "Generic", 50, "iot-restricted", "online", "low"),
  iot(ID.p3, "Conf Room Display", "Signage", "BrightSign", 40, "iot-av", "online", "low"),
  iot(ID.p4, "Pool Gate Lock", "Door Lock", "Salto", 50, "iot-restricted", "online", "low"),
  iot(ID.p5, "Hallway Camera 2F", "Camera", "Axis", 60, "iot-cameras", "offline", "high"),
  iot(ID.p6, "Stage AV Controller", "AV", "Crestron", 40, "iot-av", "online", "medium"),
  iot(ID.p7, "Badge Reader Lobby", "Access Control", "HID", 50, "iot-restricted", "online", "medium"),
  iot(ID.p8, "Thermostat Suite-09", "HVAC", "Honeywell", 50, "iot-restricted", "online", "low"),
];

function iot(
  propertyId: string,
  name: string,
  type: string,
  vendor: string,
  vlan: number,
  group: string,
  status: IotDevice["status"],
  risk: IotDevice["riskLevel"]
): IotDevice {
  return {
    id: crypto.randomUUID(),
    propertyId,
    name,
    deviceType: type,
    vendor,
    macAddress: null,
    vlan,
    ssid: null,
    securityGroup: group,
    status,
    riskLevel: risk,
    lastSeen: d("2026-06-10T14:50:00Z"),
    createdAt: d("2026-01-15T00:00:00Z"),
  };
}

// --- Alerts ------------------------------------------------------------------

export const alerts: Alert[] = [
  alert(ID.p1, "critical", "Access point Pool-AP-04 is down", "ap_down", "AP stopped responding 6h ago.", "2026-06-10T09:12:00Z"),
  alert(ID.p1, "critical", "Guest WiFi captive portal failing", "guest_wifi", "30% of guest logins failing at Harborview.", "2026-06-10T11:40:00Z"),
  alert(ID.p1, "warning", "Firmware out of date on 2 APs", "firmware", "Lobby-AP-01, Pool-AP-04 behind recommended 10.6.0.2.", "2026-06-09T22:00:00Z"),
  alert(ID.p1, "warning", "IP Camera East-Hall offline", "iot", "High-risk IoT device unreachable.", "2026-06-10T08:05:00Z"),
  alert(ID.p1, "info", "Channel utilization high in Conf room", "rf", "Conf-AP-07 at 78% utilization during event.", "2026-06-10T13:00:00Z"),
  alert(ID.p2, "warning", "Elevated guest complaints", "guest_wifi", "3 slow-WiFi tickets in 24h.", "2026-06-10T10:15:00Z"),
  alert(ID.p3, "info", "Scheduled firmware upgrade completed", "firmware", "Floor3-AP-12 upgraded to 10.6.0.2.", "2026-06-09T03:00:00Z"),
  // Meraki — Sunset Bay
  alert(ID.p4, "warning", "Firmware out of date on MR57", "firmware", "Pool-AP-03 on 29.7.1, recommended 30.7.", "2026-06-09T20:00:00Z", "meraki"),
  // UniFi — Walnut Boutique
  alert(ID.p5, "critical", "Access point WingB-AP-02 is down", "ap_down", "U7-Pro offline since 07:30.", "2026-06-10T07:30:00Z", "unifi"),
  alert(ID.p5, "warning", "Hallway Camera 2F offline", "iot", "High-risk IoT camera unreachable.", "2026-06-10T08:10:00Z", "unifi"),
  // RUCKUS — Grand Prairie
  alert(ID.p6, "info", "High client density in main hall", "rf", "Hall-AP-01 serving 88 clients during event.", "2026-06-10T13:30:00Z", "ruckus"),
  // Fortinet — Ironside
  alert(ID.p7, "warning", "Firmware out of date on FAP-231F", "firmware", "Floor4-AP-02 on 7.2.1, recommended 7.4.3.", "2026-06-09T21:00:00Z", "fortinet"),
];

function alert(
  propertyId: string,
  severity: Alert["severity"],
  title: string,
  category: string,
  description: string,
  raisedAt: string,
  source = "aruba_central"
): Alert {
  return {
    id: crypto.randomUUID(),
    propertyId,
    severity,
    status: "open",
    title,
    description,
    source,
    category,
    externalId: null,
    raisedAt: d(raisedAt),
    resolvedAt: null,
  };
}

// --- Incidents ---------------------------------------------------------------

export const incidents: Incident[] = [
  {
    id: crypto.randomUUID(),
    propertyId: ID.p1,
    title: "Recurring guest WiFi outages — Harborview",
    summary: "Captive portal + Pool-AP-04 failures recurring over the past week.",
    status: "investigating",
    severity: "critical",
    openedAt: d("2026-06-08T12:00:00Z"),
    resolvedAt: null,
  },
  {
    id: crypto.randomUUID(),
    propertyId: ID.p2,
    title: "Intermittent slowness — Cedar Ridge Wing A",
    summary: "Guests reporting slow speeds evenings; suspected capacity.",
    status: "open",
    severity: "warning",
    openedAt: d("2026-06-09T18:00:00Z"),
    resolvedAt: null,
  },
];

// --- Vendors -----------------------------------------------------------------

export const vendors: Vendor[] = [
  vendor("NorthNet Managed Services", "MSP", "Dana Cole", "dana@northnet.example", "+1-555-0142"),
  vendor("Atlantic Telecom", "ISP / Telecom", "Support Desk", "noc@atlantictel.example", "+1-555-0199"),
  vendor("HPE Aruba", "Hardware", "Channel Rep", "rep@aruba.example", "+1-555-0110"),
  vendor("Salto Systems", "IoT / Access Control", "Field Eng", "support@salto.example", "+1-555-0177"),
];

function vendor(
  name: string,
  category: string,
  contact: string,
  email: string,
  phone: string
): Vendor {
  return {
    id: crypto.randomUUID(),
    companyId: ID.company,
    name,
    category,
    contactName: contact,
    contactEmail: email,
    contactPhone: phone,
    escalationContact: null,
    createdAt: d("2026-01-05T00:00:00Z"),
  };
}

// --- Projects ----------------------------------------------------------------

export const projects: Project[] = [
  project("Harborview guest WiFi remediation", ID.p1, "in_progress", "2026-06-20T00:00:00Z", "Replace Pool-AP-04, fix captive portal."),
  project("Fleet firmware upgrade to 10.6.0.2", null, "in_progress", "2026-06-30T00:00:00Z", "Roll recommended firmware across all APs."),
  project("Cedar Ridge capacity survey", ID.p2, "planning", "2026-07-15T00:00:00Z", "RF survey for evening congestion."),
  project("IoT VLAN segmentation audit", null, "blocked", "2026-06-12T00:00:00Z", "Awaiting NAC policy export from MSP."),
];

function project(
  name: string,
  propertyId: string | null,
  status: Project["status"],
  due: string,
  description: string
): Project {
  return {
    id: crypto.randomUUID(),
    companyId: ID.company,
    propertyId,
    vendorId: null,
    name,
    description,
    status,
    dueDate: d(due),
    createdAt: d("2026-05-20T00:00:00Z"),
  };
}
