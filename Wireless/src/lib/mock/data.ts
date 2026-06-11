import type {
  Company,
  Property,
  Integration,
  AccessPoint,
  Client,
  IotDevice,
  Alert,
  Incident,
  IncidentNote,
  Circuit,
  ProjectMilestone,
  ProjectChecklistItem,
  HealthSnapshot,
  Vendor,
  Project,
} from "@/db/schema";

/**
 * Canonical in-memory dataset. Typed against the Drizzle-inferred schema types,
 * so it is structurally identical to what the database returns. The queries
 * layer (lib/queries.ts) reads from here today; swapping to Postgres later means
 * changing only that file.
 */

// Shorthand to turn an ISO date string into a real Date object. Used everywhere
// below so the fixtures read more like plain data than constructor calls.
const d = (iso: string) => new Date(iso);

// Stable ids so links work across page loads.
// Hard-coded UUIDs for the company and each property. Because they never change,
// URLs like /property/<id> keep working between reloads (unlike random ids).
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
  i1: "00000000-0000-0000-0000-0000000000c1", // Harborview guest-wifi incident
  i2: "00000000-0000-0000-0000-0000000000c2", // Cedar Ridge slowness incident
  v1: "00000000-0000-0000-0000-0000000000d1", // NorthNet MSP
  v2: "00000000-0000-0000-0000-0000000000d2", // Atlantic Telecom
  v3: "00000000-0000-0000-0000-0000000000d3", // HPE Aruba
  v4: "00000000-0000-0000-0000-0000000000d4", // Salto
  pr1: "00000000-0000-0000-0000-0000000000e1", // Harborview remediation project
  pr2: "00000000-0000-0000-0000-0000000000e2", // Fleet firmware upgrade
  pr3: "00000000-0000-0000-0000-0000000000e3", // Cedar Ridge survey
  pr4: "00000000-0000-0000-0000-0000000000e4", // IoT VLAN audit
} as const;

// The tenant company. Just one in the mock — the parent org all properties belong to.
export const companies: Company[] = [
  {
    id: ID.company,
    name: "Coastline Hospitality Group",
    slug: "coastline",
    createdAt: d("2026-01-04T00:00:00Z"),
  },
];

// The eight demo properties. The first three (Aruba-managed) are spelled out in full
// to show every field; the remaining five use the prop() helper below to stay concise.
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
  // The remaining five properties, one per non-Aruba vendor, built via the helper below.
  prop(ID.p4, "Sunset Bay Resort", "12 Ocean Dr", "Miami", "FL", "America/New_York", "meraki"),
  prop(ID.p5, "The Walnut Boutique Hotel", "55 Walnut St", "Denver", "CO", "America/Denver", "unifi"),
  prop(ID.p6, "Grand Prairie Convention Hotel", "900 Expo Blvd", "Dallas", "TX", "America/Chicago", "ruckus"),
  prop(ID.p7, "Ironside Business Center", "70 Wacker Dr", "Chicago", "IL", "America/Chicago", "fortinet"),
  prop(ID.p8, "Lakeshore Suites", "230 Lakeshore Ave", "Seattle", "WA", "America/Los_Angeles", "mist"),
];

// Helper that fills in a full Property row from just the fields that vary, so the
// list above stays readable. The constant fields (companyId, createdAt, etc.) are baked in.
function prop(
  id: string,
  name: string,
  address: string,
  city: string,
  region: string,
  timezone: string,
  managedBy: Property["managedBy"] // restricts managedBy to the valid vendor names from the schema
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

// One integration per vendor: how the app connects to each manufacturer's cloud API.
// Aruba is written out in full (and uses the stable id so links work); the other five
// use the integration() helper. All are marked "connected" in the demo.
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

// Helper to build a connected integration row, defaulting the boilerplate fields
// (status, credentials, sync times). Each call gets a fresh random id.
function integration(
  vendor: Integration["vendor"],
  label: string,
  baseUrl: string
): Integration {
  return {
    id: crypto.randomUUID(), // generate a random UUID for this row at module load
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

// Wi-Fi access points across all properties, built with the ap() helper. Statuses
// (online/offline/degraded) and firmware values are deliberately mixed so the health
// score and firmware-lag tracker have realistic problems to surface. Grouped by vendor.
export const accessPoints: AccessPoint[] = [
  // Aruba properties (p1 Harborview, p2 Cedar Ridge, p3 Metro): includes one offline
  // and one degraded AP at Harborview to drive its lower score.
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

// Helper to build one access point row. Takes just the interesting fields
// (property, name, model, status, installed firmware `fw`, recommended firmware
// `fwRec`, client count, uptime, last-seen) and fills in the rest as nulls/defaults.
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
    firmwareVersion: fw, // what's actually installed
    firmwareRecommended: fwRec, // what it should be on; if these differ, it's flagged as lagging
    clientCount,
    uptimeSeconds: uptime,
    lastSeen: d(lastSeen), // parse the ISO string into a Date
    externalId: null,
    createdAt: d("2026-01-10T00:00:00Z"),
  };
}

// --- Clients -----------------------------------------------------------------

// Connected client devices (phones, laptops, POS terminals) — roughly one or two per
// property. A few guests are marked failed/degraded so guest-failure penalties appear.
// signal is in dBm (closer to 0 is stronger; -80 is weak).
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

// Helper to build one client row. Note isGuest/failed are passed as friendly booleans
// here but stored as 0/1 integers below (the DB schema uses integer flags).
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
    isGuest: isGuest ? 1 : 0, // boolean -> 0/1 integer flag
    signalDbm: signal,
    status,
    connectionFailed: failed ? 1 : 0, // boolean -> 0/1 integer flag (feeds guest-failure scoring)
    lastSeen: d("2026-06-10T14:54:00Z"),
    createdAt: d("2026-06-01T00:00:00Z"),
  };
}

// --- IoT devices -------------------------------------------------------------

// Non-PC "smart" devices (locks, thermostats, cameras, signage). Each sits on a VLAN
// and a security group. Two high-risk cameras are offline to trigger IoT-failure penalties.
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
  // SEGMENTATION VIOLATIONS — exercise the IoT security detections:
  // 1) The critical case: an unknown, unapproved device sitting on the STAFF
  //    network (corp zone, no NAC policy) → "move to IoT VLAN or quarantine".
  iot(ID.p1, "Unknown Device 4C:7A:9B", "Unknown", "Unknown", 10, "staff", "online", "critical", {
    ssid: "Harborview-Staff",
    firewallZone: "corp",
    nacPolicy: null,
    owner: null,
    approval: "unapproved",
  }),
  // 2) A known device type that was never approved, also off the IoT segment.
  iot(ID.p7, "Lobby Kiosk 2", "Kiosk", "Elo", 10, "staff", "online", "medium", {
    ssid: "Ironside-Staff",
    firewallZone: "corp",
    nacPolicy: null,
    owner: null,
    approval: "unapproved",
  }),
];

// Helper to build one IoT device row. `vlan` and `group` describe its network
// segmentation; `risk` (low/medium/high) reflects how dangerous it is if compromised.
// `extras` overrides the segmentation defaults (zone/NAC/owner/approval/ssid) —
// the defaults model a correctly segmented, sanctioned device.
function iot(
  propertyId: string,
  name: string,
  type: string,
  vendor: string,
  vlan: number,
  group: string,
  status: IotDevice["status"],
  risk: IotDevice["riskLevel"],
  extras?: Partial<
    Pick<IotDevice, "firewallZone" | "nacPolicy" | "owner" | "approval" | "ssid" | "deviceType">
  >
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
    // Segmentation defaults: a well-behaved device sits in the IoT firewall
    // zone, under the restricted NAC policy, owned by Facilities, approved.
    firewallZone: "iot",
    nacPolicy: "iot-restricted",
    owner: "Facilities",
    approval: "approved",
    status,
    riskLevel: risk,
    lastSeen: d("2026-06-10T14:50:00Z"),
    createdAt: d("2026-01-15T00:00:00Z"),
    ...extras,
  };
}

// --- Alerts ------------------------------------------------------------------

// Active alerts across properties. Severity is critical/warning/info; category groups
// them (ap_down, firmware, guest_wifi, iot, rf). Harborview (p1) carries the heaviest
// load to explain its low health score. Vendor source defaults to aruba_central but is
// overridden for the non-Aruba properties.
export const alerts: Alert[] = [
  alert(ID.p1, "critical", "Access point Pool-AP-04 is down", "ap_down", "AP stopped responding 6h ago.", "2026-06-10T09:12:00Z"),
  alert(ID.p1, "critical", "Guest WiFi captive portal failing", "guest_wifi", "30% of guest logins failing at Harborview.", "2026-06-10T11:40:00Z"),
  // Second guest_wifi alert at the same property within the 30-day window —
  // exercises the recurrence detection + severity escalation rules end-to-end.
  alert(ID.p1, "warning", "Guest WiFi slow in lobby", "guest_wifi", "Repeated guest complaints about lobby WiFi speed.", "2026-06-07T19:30:00Z"),
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

// Helper to build one alert row. Every mock alert starts in "open" status with no
// resolvedAt. `source` defaults to aruba_central but callers pass a vendor name for
// the other integrations.
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

// Incidents are higher-level investigations that often bundle several related alerts.
// Two demo incidents, both unresolved — and both already past their SLA deadline
// (critical = 4h, warning = 24h), so the ticketing automation's auto-escalation
// rule has something to demonstrate on the first sync.
export const incidents: Incident[] = [
  {
    id: ID.i1,
    propertyId: ID.p1,
    title: "Recurring guest WiFi outages — Harborview",
    summary: "Captive portal + Pool-AP-04 failures recurring over the past week.",
    status: "investigating",
    severity: "critical",
    category: "guest_wifi", // matches the alert category so automation sees it as covered
    alertId: null,
    owner: "Dana Cole (NorthNet MSP)",
    slaDueAt: d("2026-06-08T16:00:00Z"), // openedAt + 4h (critical SLA) — breached
    openedAt: d("2026-06-08T12:00:00Z"),
    resolvedAt: null,
  },
  {
    id: ID.i2,
    propertyId: ID.p2,
    title: "Intermittent slowness — Cedar Ridge Wing A",
    summary: "Guests reporting slow speeds evenings; suspected capacity.",
    status: "open",
    severity: "warning",
    category: "rf",
    alertId: null,
    owner: null, // unassigned — exercise the assign-owner flow
    slaDueAt: d("2026-06-10T18:00:00Z"), // openedAt + 24h (warning SLA) — breached
    openedAt: d("2026-06-09T18:00:00Z"),
    resolvedAt: null,
  },
];

// Work-log notes on the incidents (author is free text until RBAC lands).
export const incidentNotes: IncidentNote[] = [
  {
    id: crypto.randomUUID(),
    incidentId: ID.i1,
    author: "Dana Cole",
    body: "Replaced patch cable on Pool-AP-04 switch port; portal still failing intermittently. Suspecting RADIUS timeout.",
    createdAt: d("2026-06-09T15:20:00Z"),
  },
  {
    id: crypto.randomUUID(),
    incidentId: ID.i1,
    author: "ops",
    body: "Guest complaints continuing overnight. Vendor ticket #48211 opened with HPE Aruba.",
    createdAt: d("2026-06-10T08:05:00Z"),
  },
];

// --- Vendors -----------------------------------------------------------------

// Business vendors/partners (not the device manufacturers) — the MSP, ISP, hardware
// rep, and IoT supplier the company works with. Each row carries the full
// vendor-management record: contact, escalation path, contract window, SLA terms.
// Atlantic Telecom's contract ends inside 90 days to exercise the renewal warning.
export const vendors: Vendor[] = [
  vendor(ID.v1, "NorthNet Managed Services", "MSP", "Dana Cole", "dana@northnet.example", "+1-555-0142", {
    escalationContact: "Escalations: Marcus Webb, VP Ops — +1-555-0143",
    contractStart: d("2025-01-01T00:00:00Z"),
    contractEnd: d("2027-01-01T00:00:00Z"),
    slaTerms: "P1 response 30min · P2 4h · monthly health report",
  }),
  vendor(ID.v2, "Atlantic Telecom", "ISP / Telecom", "Support Desk", "noc@atlantictel.example", "+1-555-0199", {
    escalationContact: "NOC duty manager — +1-555-0190 (24/7)",
    contractStart: d("2023-08-01T00:00:00Z"),
    contractEnd: d("2026-08-01T00:00:00Z"), // < 90 days out → renewal warning
    slaTerms: "99.9% circuit uptime · 4h MTTR on fiber cuts",
  }),
  vendor(ID.v3, "HPE Aruba", "Hardware", "Channel Rep", "rep@aruba.example", "+1-555-0110", {
    escalationContact: "TAC Sev-1 hotline — +1-800-555-0111",
    contractStart: d("2025-03-01T00:00:00Z"),
    contractEnd: d("2028-03-01T00:00:00Z"),
    slaTerms: "Foundation Care NBD hardware replacement",
  }),
  vendor(ID.v4, "Salto Systems", "IoT / Access Control", "Field Eng", "support@salto.example", "+1-555-0177", {
    escalationContact: "Regional field manager — +1-555-0178",
    contractStart: d("2025-06-15T00:00:00Z"),
    contractEnd: d("2026-12-15T00:00:00Z"),
    slaTerms: "On-site within 48h for lock failures",
  }),
];

// Helper to build one vendor row; `extras` carries the contract/SLA/escalation record.
function vendor(
  id: string,
  name: string,
  category: string,
  contact: string,
  email: string,
  phone: string,
  extras?: Partial<Pick<Vendor, "escalationContact" | "contractStart" | "contractEnd" | "slaTerms">>
): Vendor {
  return {
    id,
    companyId: ID.company,
    name,
    category,
    contactName: contact,
    contactEmail: email,
    contactPhone: phone,
    escalationContact: null,
    contractStart: null,
    contractEnd: null,
    slaTerms: null,
    createdAt: d("2026-01-05T00:00:00Z"),
    ...extras,
  };
}

// --- Projects ----------------------------------------------------------------

// Work items / projects. Some are tied to a property (e.g. Harborview remediation),
// others are portfolio-wide (propertyId null, like the fleet firmware upgrade). Statuses
// span planning/in_progress/blocked to populate a project board.
export const projects: Project[] = [
  project(ID.pr1, "Harborview guest WiFi remediation", ID.p1, ID.v1, "in_progress", "2026-06-20T00:00:00Z", "Replace Pool-AP-04, fix captive portal."),
  project(ID.pr2, "Fleet firmware upgrade to 10.6.0.2", null, ID.v3, "in_progress", "2026-06-30T00:00:00Z", "Roll recommended firmware across all APs."),
  project(ID.pr3, "Cedar Ridge capacity survey", ID.p2, ID.v1, "planning", "2026-07-15T00:00:00Z", "RF survey for evening congestion."),
  project(ID.pr4, "IoT VLAN segmentation audit", null, ID.v1, "blocked", "2026-06-12T00:00:00Z", "Awaiting NAC policy export from MSP."),
];

// Helper to build one project row. propertyId may be null for portfolio-wide
// work; vendorId links the vendor doing the work.
function project(
  id: string,
  name: string,
  propertyId: string | null,
  vendorId: string | null,
  status: Project["status"],
  due: string,
  description: string
): Project {
  return {
    id,
    companyId: ID.company,
    propertyId,
    vendorId,
    name,
    description,
    status,
    dueDate: d(due),
    createdAt: d("2026-05-20T00:00:00Z"),
  };
}

// --- Circuits ------------------------------------------------------------------

// Telecom circuit inventory: each property's WAN links with the carrier's
// circuit reference, bandwidth, cost, and contract end. Harborview's LTE backup
// is degraded; Cedar Ridge's cable contract ends soon (renewal warning).
export const circuits: Circuit[] = [
  circuit(ID.p1, ID.v2, "ATL-DIA-88421", "DIA fiber", 1000, "online", 1450, "2026-08-01T00:00:00Z"),
  circuit(ID.p1, ID.v2, "ATL-LTE-88422", "LTE backup", 50, "degraded", 120, "2026-08-01T00:00:00Z"),
  circuit(ID.p2, ID.v2, "ATL-CBL-31077", "Cable broadband", 600, "online", 380, "2026-07-20T00:00:00Z"),
  circuit(ID.p4, ID.v2, "ATL-DIA-90233", "DIA fiber", 1000, "online", 1390, "2027-02-01T00:00:00Z"),
  circuit(ID.p6, ID.v2, "ATL-DIA-77810", "DIA fiber", 2000, "online", 2100, "2027-05-01T00:00:00Z"),
];

// Helper to build one circuit row.
function circuit(
  propertyId: string,
  vendorId: string,
  ref: string,
  type: string,
  mbps: number,
  status: Circuit["status"],
  cost: number,
  contractEnd: string
): Circuit {
  return {
    id: crypto.randomUUID(),
    propertyId,
    vendorId,
    circuitRef: ref,
    type,
    bandwidthMbps: mbps,
    status,
    monthlyCost: cost,
    contractEnd: d(contractEnd),
    createdAt: d("2026-01-05T00:00:00Z"),
  };
}

// --- Project milestones & checklists --------------------------------------------

// Milestones for the Harborview remediation (2 done, 1 pending) and the fleet
// firmware upgrade (1 done, 2 pending) — enough to render real progress bars.
export const projectMilestones: ProjectMilestone[] = [
  milestone(ID.pr1, "Site survey + RF audit", "2026-06-10T00:00:00Z", "2026-06-09T16:00:00Z", 0),
  milestone(ID.pr1, "Replacement AP staged & configured", "2026-06-14T00:00:00Z", "2026-06-11T01:00:00Z", 1),
  milestone(ID.pr1, "Cutover + portal fix", "2026-06-18T00:00:00Z", null, 2),
  milestone(ID.pr2, "Pilot upgrade — Metro Business Suites", "2026-06-08T00:00:00Z", "2026-06-09T03:30:00Z", 0),
  milestone(ID.pr2, "Wave 1 — Aruba properties", "2026-06-20T00:00:00Z", null, 1),
  milestone(ID.pr2, "Wave 2 — remaining vendors", "2026-06-28T00:00:00Z", null, 2),
];

function milestone(
  projectId: string,
  name: string,
  due: string,
  completed: string | null,
  sortOrder: number
): ProjectMilestone {
  return {
    id: crypto.randomUUID(),
    projectId,
    name,
    dueDate: d(due),
    completedAt: completed ? d(completed) : null,
    sortOrder,
  };
}

// Cutover + post-deployment validation checklist for the Harborview remediation.
export const projectChecklist: ProjectChecklistItem[] = [
  check(ID.pr1, "cutover", "Maintenance window approved by GM", 1, 0),
  check(ID.pr1, "cutover", "Config backup taken (controller + portal)", 1, 1),
  check(ID.pr1, "cutover", "Swap Pool-AP-04 hardware", 0, 2),
  check(ID.pr1, "cutover", "Re-point captive portal to new RADIUS pool", 0, 3),
  check(ID.pr1, "validation", "Guest login succeeds end-to-end on 3 devices", 0, 0),
  check(ID.pr1, "validation", "Roaming test lobby → pool deck passes", 0, 1),
  check(ID.pr1, "validation", "Health score recovers above 60 within 24h", 0, 2),
];

function check(
  projectId: string,
  phase: string,
  label: string,
  done: number,
  sortOrder: number
): ProjectChecklistItem {
  return { id: crypto.randomUUID(), projectId, phase, label, done, sortOrder };
}

// --- Health score history --------------------------------------------------------

// Eight daily snapshots per property (Jun 3-10) — the "before/after" story.
// Harborview is the headline: 91 a week ago, collapsing to ~30 as the AP died,
// the captive portal failed, and the rogue IoT device appeared. Walnut shows a
// slower slide; everyone else holds steady. Trajectories end near each
// property's live computed score so the trend reads as one continuous story.
const SCORE_SERIES: Record<string, number[]> = {
  [ID.p1]: [91, 88, 84, 76, 62, 48, 35, 30], // Harborview — the demo headline
  [ID.p5]: [89, 87, 84, 80, 72, 66, 60, 55], // Walnut — slow degradation
  [ID.p2]: [97, 96, 96, 95, 94, 93, 92, 92], // Cedar Ridge — mild wobble
  [ID.p3]: [100, 100, 100, 100, 100, 100, 100, 100], // Metro — rock solid
  [ID.p4]: [93, 94, 92, 93, 91, 92, 91, 91], // Sunset Bay
  [ID.p6]: [98, 97, 98, 99, 98, 99, 99, 100], // Grand Prairie
  [ID.p7]: [95, 94, 93, 92, 92, 91, 91, 91], // Ironside
  [ID.p8]: [99, 99, 98, 99, 100, 99, 100, 100], // Lakeshore
};

export const healthSnapshots: HealthSnapshot[] = Object.entries(SCORE_SERIES).flatMap(
  ([propertyId, scores]) =>
    scores.map((score, i) => ({
      id: crypto.randomUUID(),
      propertyId,
      score,
      // Day i maps to June (3+i), all sampled at 06:00 UTC.
      at: d(`2026-06-${String(3 + i).padStart(2, "0")}T06:00:00Z`),
    }))
);
