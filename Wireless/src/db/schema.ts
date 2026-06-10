import {
  pgTable,
  pgEnum,
  uuid,
  text,
  integer,
  timestamp,
  jsonb,
  index,
} from "drizzle-orm/pg-core";

/**
 * Database schema — single source of truth for the platform's data model.
 *
 * Scope: the first slice (Aruba Central + hotel WiFi + IoT inventory).
 * Multi-vendor (Meraki, UniFi, Ruckus, Fortinet, Mist) reuses these same
 * tables; only the `integrations.vendor` value and the adapter differ.
 *
 * TypeScript types are inferred from these tables (see exports at the bottom)
 * and shared by both the mock data layer and the eventual DB-backed queries,
 * so the UI never drifts from the schema.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export const alertSeverity = pgEnum("alert_severity", ["critical", "warning", "info"]);
export const alertStatus = pgEnum("alert_status", ["open", "acknowledged", "resolved"]);
export const deviceStatus = pgEnum("device_status", ["online", "offline", "degraded"]);
export const riskLevel = pgEnum("risk_level", ["low", "medium", "high", "critical"]);
export const incidentStatus = pgEnum("incident_status", ["open", "investigating", "resolved"]);
export const projectStatus = pgEnum("project_status", [
  "planning",
  "in_progress",
  "blocked",
  "completed",
]);
export const integrationVendor = pgEnum("integration_vendor", [
  "aruba_central",
  "meraki",
  "unifi",
  "ruckus",
  "fortinet",
  "mist",
]);
export const integrationStatus = pgEnum("integration_status", [
  "connected",
  "disconnected",
  "error",
  "not_configured",
]);

// ---------------------------------------------------------------------------
// Core tenancy
// ---------------------------------------------------------------------------

export const companies = pgTable("companies", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull().unique(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const properties = pgTable(
  "properties",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    address: text("address"),
    city: text("city"),
    region: text("region"),
    timezone: text("timezone"),
    // Cached 0-100 health score; recomputed by the analytics job.
    healthScore: integer("health_score").notNull().default(100),
    // The network vendor that manages this site's WiFi (multi-vendor portfolio).
    managedBy: integrationVendor("managed_by"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("properties_company_idx").on(t.companyId)]
);

// ---------------------------------------------------------------------------
// Vendor integrations (Aruba Central first)
// ---------------------------------------------------------------------------

export const integrations = pgTable(
  "integrations",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    vendor: integrationVendor("vendor").notNull(),
    label: text("label").notNull(),
    status: integrationStatus("status").notNull().default("not_configured"),
    baseUrl: text("base_url"),
    // Encrypted credential blob (client id/secret, customer id, refresh token).
    // Never store secrets in plaintext in production.
    credentials: jsonb("credentials").$type<Record<string, string>>(),
    lastSyncedAt: timestamp("last_synced_at", { withTimezone: true }),
    lastError: text("last_error"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("integrations_company_idx").on(t.companyId)]
);

// ---------------------------------------------------------------------------
// Network inventory
// ---------------------------------------------------------------------------

export const accessPoints = pgTable(
  "access_points",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    model: text("model"),
    serial: text("serial"),
    macAddress: text("mac_address"),
    ipAddress: text("ip_address"),
    status: deviceStatus("status").notNull().default("online"),
    firmwareVersion: text("firmware_version"),
    // Latest recommended firmware for this model; drives the lifecycle tracker.
    firmwareRecommended: text("firmware_recommended"),
    clientCount: integer("client_count").notNull().default(0),
    uptimeSeconds: integer("uptime_seconds").notNull().default(0),
    lastSeen: timestamp("last_seen", { withTimezone: true }),
    // External id from the source vendor (e.g. Aruba AP serial/id).
    externalId: text("external_id"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("aps_property_idx").on(t.propertyId)]
);

export const clients = pgTable(
  "clients",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    accessPointId: uuid("access_point_id").references(() => accessPoints.id, {
      onDelete: "set null",
    }),
    hostname: text("hostname"),
    macAddress: text("mac_address"),
    ssid: text("ssid"),
    // Whether this client is on the guest network (guest WiFi module).
    isGuest: integer("is_guest").notNull().default(0),
    signalDbm: integer("signal_dbm"),
    status: deviceStatus("status").notNull().default("online"),
    connectionFailed: integer("connection_failed").notNull().default(0),
    lastSeen: timestamp("last_seen", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("clients_property_idx").on(t.propertyId)]
);

export const iotDevices = pgTable(
  "iot_devices",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    deviceType: text("device_type"),
    vendor: text("vendor"),
    macAddress: text("mac_address"),
    vlan: integer("vlan"),
    ssid: text("ssid"),
    securityGroup: text("security_group"),
    status: deviceStatus("status").notNull().default("online"),
    riskLevel: riskLevel("risk_level").notNull().default("low"),
    lastSeen: timestamp("last_seen", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("iot_property_idx").on(t.propertyId)]
);

// ---------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------

export const alerts = pgTable(
  "alerts",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    severity: alertSeverity("severity").notNull(),
    status: alertStatus("status").notNull().default("open"),
    title: text("title").notNull(),
    description: text("description"),
    source: text("source"),
    // Category groups recurring issues (e.g. "guest_wifi", "firmware", "ap_down").
    category: text("category"),
    externalId: text("external_id"),
    raisedAt: timestamp("raised_at", { withTimezone: true }).notNull().defaultNow(),
    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  },
  (t) => [
    index("alerts_property_idx").on(t.propertyId),
    index("alerts_severity_idx").on(t.severity),
  ]
);

export const incidents = pgTable(
  "incidents",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    propertyId: uuid("property_id").references(() => properties.id, {
      onDelete: "cascade",
    }),
    title: text("title").notNull(),
    summary: text("summary"),
    status: incidentStatus("status").notNull().default("open"),
    severity: alertSeverity("severity").notNull().default("warning"),
    openedAt: timestamp("opened_at", { withTimezone: true }).notNull().defaultNow(),
    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  },
  (t) => [index("incidents_property_idx").on(t.propertyId)]
);

// ---------------------------------------------------------------------------
// Vendor / project tracking
// ---------------------------------------------------------------------------

export const vendors = pgTable(
  "vendors",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    category: text("category"), // MSP, ISP/telecom, hardware, etc.
    contactName: text("contact_name"),
    contactEmail: text("contact_email"),
    contactPhone: text("contact_phone"),
    escalationContact: text("escalation_contact"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("vendors_company_idx").on(t.companyId)]
);

export const projects = pgTable(
  "projects",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    propertyId: uuid("property_id").references(() => properties.id, {
      onDelete: "set null",
    }),
    vendorId: uuid("vendor_id").references(() => vendors.id, { onDelete: "set null" }),
    name: text("name").notNull(),
    description: text("description"),
    status: projectStatus("status").notNull().default("planning"),
    dueDate: timestamp("due_date", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("projects_company_idx").on(t.companyId)]
);

// ---------------------------------------------------------------------------
// Inferred types — shared by mock data, queries, and UI.
// ---------------------------------------------------------------------------

export type Company = typeof companies.$inferSelect;
export type Property = typeof properties.$inferSelect;
export type Integration = typeof integrations.$inferSelect;
export type AccessPoint = typeof accessPoints.$inferSelect;
export type Client = typeof clients.$inferSelect;
export type IotDevice = typeof iotDevices.$inferSelect;
export type Alert = typeof alerts.$inferSelect;
export type Incident = typeof incidents.$inferSelect;
export type Vendor = typeof vendors.$inferSelect;
export type Project = typeof projects.$inferSelect;

export type Severity = (typeof alertSeverity.enumValues)[number];
export type DeviceState = (typeof deviceStatus.enumValues)[number];
export type Risk = (typeof riskLevel.enumValues)[number];
export type IntegrationVendorName = (typeof integrationVendor.enumValues)[number];
