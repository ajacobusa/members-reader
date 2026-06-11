// These are Drizzle's Postgres "column/table builders". Each one is a small
// helper used to declare a table or a column of a specific SQL type:
import {
  pgTable, // defines a Postgres table
  pgEnum, // defines a Postgres ENUM type (a fixed list of allowed string values)
  uuid, // a UUID column (128-bit unique id, often used for primary keys)
  text, // a variable-length text/string column
  integer, // a whole-number column
  timestamp, // a date+time column
  jsonb, // a binary-JSON column (stores arbitrary JSON, queryable)
  index, // declares an index on one or more columns (speeds up lookups)
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

// Each pgEnum creates a database ENUM: a column using it may ONLY hold one of
// the listed strings. The first argument is the type name in Postgres; the
// array is the allowed values. Using enums keeps invalid states out of the DB.

// How urgent an alert is, from most to least severe.
export const alertSeverity = pgEnum("alert_severity", ["critical", "warning", "info"]);
// Where an alert is in its lifecycle: newly opened, seen by an operator, or fixed.
export const alertStatus = pgEnum("alert_status", ["open", "acknowledged", "resolved"]);
// Operational state of a device: fully up, down, or partially working.
export const deviceStatus = pgEnum("device_status", ["online", "offline", "degraded"]);
// Security risk rating for an IoT device.
export const riskLevel = pgEnum("risk_level", ["low", "medium", "high", "critical"]);
// Where an incident is in its lifecycle.
// Incident workflow states. "vendor_escalated" = handed to the responsible
// vendor/MSP (appended last so the migration is a simple ADD VALUE).
export const incidentStatus = pgEnum("incident_status", [
  "open",
  "investigating",
  "resolved",
  "vendor_escalated",
]);
// Lifecycle stages for a project (rollout, install, etc.).
export const projectStatus = pgEnum("project_status", [
  "planning",
  "in_progress",
  "blocked",
  "completed",
]);
// The supported network-equipment vendors. The whole platform is multi-vendor;
// this enum is how a property/integration records which one manages it.
export const integrationVendor = pgEnum("integration_vendor", [
  "aruba_central",
  "meraki",
  "unifi",
  "ruckus",
  "fortinet",
  "mist",
]);
// Connection state of a vendor integration (is the API link healthy?).
// Platform roles for RBAC (see lib/authz.ts for the permission matrix).
export const memberRole = pgEnum("member_role", [
  "owner",
  "admin",
  "network_engineer",
  "property_manager",
  "vendor_msp",
  "readonly_exec",
]);
// IoT device approval lifecycle: approved (known + sanctioned), unapproved
// (newly seen / not yet reviewed), quarantined (isolated pending investigation).
export const iotApproval = pgEnum("iot_approval", [
  "approved",
  "unapproved",
  "quarantined",
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

// A company is the top-level tenant: every other record ultimately belongs to one.
export const companies = pgTable("companies", {
  // Primary key. `defaultRandom()` auto-generates a random UUID for new rows.
  id: uuid("id").defaultRandom().primaryKey(),
  // Human-readable company name. `notNull()` means it must always be provided.
  name: text("name").notNull(),
  // URL-friendly unique identifier (e.g. "acme-hotels"). `unique()` forbids
  // two companies from sharing the same slug.
  slug: text("slug").notNull().unique(),
  // When the row was created. `withTimezone: true` stores the zone; `defaultNow()`
  // fills in the current time automatically on insert.
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// A property is a physical site (e.g. one hotel) belonging to a company.
// The second pgTable argument is an array of extra table-level options (indexes).
export const properties = pgTable(
  "properties",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // Foreign key to the owning company. `.references(...)` links this column to
    // companies.id; `onDelete: "cascade"` means deleting a company also deletes
    // its properties. `notNull()` makes the link mandatory.
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    // Site name (required).
    name: text("name").notNull(),
    // Optional postal address (no notNull, so it may be empty/NULL).
    address: text("address"),
    // Optional city.
    city: text("city"),
    // Optional region/state.
    region: text("region"),
    // Optional IANA timezone string (e.g. "America/New_York").
    timezone: text("timezone"),
    // Cached 0-100 health score; recomputed by the analytics job.
    // Defaults to 100 (perfectly healthy) until the job runs.
    healthScore: integer("health_score").notNull().default(100),
    // The network vendor that manages this site's WiFi (multi-vendor portfolio).
    // Uses the integrationVendor enum; nullable because it may be unknown.
    managedBy: integrationVendor("managed_by"),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index on company_id so "all properties for a company" queries are fast.
  (t) => [index("properties_company_idx").on(t.companyId)]
);

// ---------------------------------------------------------------------------
// Vendor integrations (Aruba Central first)
// ---------------------------------------------------------------------------

// An integration is a configured link to a vendor's cloud API (e.g. Aruba
// Central) for one company. It stores how to connect and the link's health.
export const integrations = pgTable(
  "integrations",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // Owning company; deletes cascade when the company is removed.
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    // Which vendor this integration talks to (required enum value).
    vendor: integrationVendor("vendor").notNull(),
    // A friendly display name for this connection (required).
    label: text("label").notNull(),
    // Current connection health; new integrations start "not_configured".
    status: integrationStatus("status").notNull().default("not_configured"),
    // Optional API base URL (region-specific endpoints differ per vendor).
    baseUrl: text("base_url"),
    // Encrypted credential blob (client id/secret, customer id, refresh token).
    // Never store secrets in plaintext in production.
    // `.$type<...>()` tells TypeScript the JSON's shape (a string→string map)
    // without changing how it's stored in Postgres. Nullable until configured.
    credentials: jsonb("credentials").$type<Record<string, string>>(),
    // When data was last successfully pulled from the vendor (nullable: may never).
    lastSyncedAt: timestamp("last_synced_at", { withTimezone: true }),
    // Last error message from a failed sync, for troubleshooting (nullable).
    lastError: text("last_error"),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index for fast "all integrations for a company" lookups.
  (t) => [index("integrations_company_idx").on(t.companyId)]
);

// One row per sync attempt — the audit log for vendor data pulls. Failures are
// recorded here (and mirrored onto integrations.lastError) so operators can see
// exactly when a vendor link broke and why.
export const syncRuns = pgTable(
  "sync_runs",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The integration this run belonged to; removed with the integration.
    integrationId: uuid("integration_id")
      .notNull()
      .references(() => integrations.id, { onDelete: "cascade" }),
    // When the run started / finished (finished is null while in flight).
    startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
    finishedAt: timestamp("finished_at", { withTimezone: true }),
    // 1 = succeeded, 0 = failed (integer flag, same convention as elsewhere).
    ok: integer("ok").notNull().default(0),
    // Human-readable error when the run failed (nullable on success).
    error: text("error"),
    // Per-run statistics, e.g. {"sites":2,"aps":5,"clients":12,"alerts":3}.
    stats: jsonb("stats").$type<Record<string, number>>(),
  },
  (t) => [index("sync_runs_integration_idx").on(t.integrationId)]
);

// ---------------------------------------------------------------------------
// Network inventory
// ---------------------------------------------------------------------------

// An access point (AP) is a physical WiFi radio installed at a property.
export const accessPoints = pgTable(
  "access_points",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The property this AP is installed at; deletes cascade with the property.
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    // AP display name/label (required).
    name: text("name").notNull(),
    // Hardware model (optional).
    model: text("model"),
    // Manufacturer serial number (optional).
    serial: text("serial"),
    // Hardware MAC address (optional).
    macAddress: text("mac_address"),
    // Current IP address on the network (optional).
    ipAddress: text("ip_address"),
    // Operational state; new APs default to "online".
    status: deviceStatus("status").notNull().default("online"),
    // Firmware version currently running on the device (optional).
    firmwareVersion: text("firmware_version"),
    // Latest recommended firmware for this model; drives the lifecycle tracker.
    // Comparing this to firmwareVersion shows which APs need an update.
    firmwareRecommended: text("firmware_recommended"),
    // How many clients are currently connected; defaults to 0.
    clientCount: integer("client_count").notNull().default(0),
    // How long the AP has been up, in seconds; defaults to 0.
    uptimeSeconds: integer("uptime_seconds").notNull().default(0),
    // When the AP was last observed reporting in (nullable).
    lastSeen: timestamp("last_seen", { withTimezone: true }),
    // External id from the source vendor (e.g. Aruba AP serial/id).
    // Lets us match this row back to the record in the vendor's system.
    externalId: text("external_id"),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index for fast "all APs at a property" lookups.
  (t) => [index("aps_property_idx").on(t.propertyId)]
);

// A client is an end-user device (phone, laptop, etc.) connected to the WiFi.
export const clients = pgTable(
  "clients",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The property the client is connected at; deletes cascade with the property.
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    // The AP the client is associated with. `onDelete: "set null"` keeps the
    // client row but clears this link if the AP is deleted. Nullable (no notNull).
    accessPointId: uuid("access_point_id").references(() => accessPoints.id, {
      onDelete: "set null",
    }),
    // Device hostname if known (optional).
    hostname: text("hostname"),
    // Device MAC address (optional).
    macAddress: text("mac_address"),
    // The WiFi network name the client joined (optional).
    ssid: text("ssid"),
    // Whether this client is on the guest network (guest WiFi module).
    // Stored as an integer flag: 0 = no, 1 = yes (defaults to 0).
    isGuest: integer("is_guest").notNull().default(0),
    // Signal strength in dBm (negative numbers; closer to 0 is stronger). Nullable.
    signalDbm: integer("signal_dbm"),
    // Connection state; defaults to "online".
    status: deviceStatus("status").notNull().default("online"),
    // Flag for a failed connection attempt: 0 = ok, 1 = failed (defaults to 0).
    connectionFailed: integer("connection_failed").notNull().default(0),
    // When the client was last seen on the network (nullable).
    lastSeen: timestamp("last_seen", { withTimezone: true }),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index for fast "all clients at a property" lookups.
  (t) => [index("clients_property_idx").on(t.propertyId)]
);

// An IoT device is a non-user "thing" on the network (smart TV, lock, sensor,
// thermostat, etc.) tracked separately for inventory and security.
export const iotDevices = pgTable(
  "iot_devices",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The property the device lives at; deletes cascade with the property.
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    // Device display name (required).
    name: text("name").notNull(),
    // Free-text category, e.g. "thermostat" or "camera" (optional).
    deviceType: text("device_type"),
    // Device manufacturer as free text (optional; note: not the network vendor enum).
    vendor: text("vendor"),
    // Device MAC address (optional).
    macAddress: text("mac_address"),
    // VLAN id the device sits on, used for network segmentation (optional).
    vlan: integer("vlan"),
    // The WiFi network name the device uses (optional).
    ssid: text("ssid"),
    // Named security/policy group the device belongs to (optional).
    securityGroup: text("security_group"),
    // Firewall zone the device's segment maps to, e.g. "iot" or "corp" (optional).
    firewallZone: text("firewall_zone"),
    // NAC (network access control) policy applied to the device (optional).
    nacPolicy: text("nac_policy"),
    // Who owns/operates the device, e.g. "Facilities" or a vendor name (optional).
    owner: text("owner"),
    // Approval lifecycle: newly discovered devices start "unapproved" until an
    // operator reviews them; "quarantined" means isolated pending investigation.
    approval: iotApproval("approval").notNull().default("unapproved"),
    // Operational state; defaults to "online".
    status: deviceStatus("status").notNull().default("online"),
    // Security risk rating; new devices default to "low".
    riskLevel: riskLevel("risk_level").notNull().default("low"),
    // When the device was last seen on the network (nullable).
    lastSeen: timestamp("last_seen", { withTimezone: true }),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index for fast "all IoT devices at a property" lookups.
  (t) => [index("iot_property_idx").on(t.propertyId)]
);

// ---------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------

// An alert is a single notable event raised about a property (e.g. an AP went
// down). Alerts can later be grouped/escalated into incidents.
export const alerts = pgTable(
  "alerts",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The affected property; deletes cascade with the property.
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    // How urgent the alert is (required enum value).
    severity: alertSeverity("severity").notNull(),
    // Lifecycle state; new alerts start "open".
    status: alertStatus("status").notNull().default("open"),
    // Short summary line (required).
    title: text("title").notNull(),
    // Longer details (optional).
    description: text("description"),
    // Where the alert came from, e.g. a system or sensor name (optional).
    source: text("source"),
    // Category groups recurring issues (e.g. "guest_wifi", "firmware", "ap_down").
    category: text("category"),
    // Matching id in the source vendor's system, for de-duplication (optional).
    externalId: text("external_id"),
    // When the alert was first raised; auto-set to now on insert.
    raisedAt: timestamp("raised_at", { withTimezone: true }).notNull().defaultNow(),
    // When the alert was resolved; stays NULL while still open.
    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  },
  // Two indexes: one to fetch a property's alerts, one to filter by severity.
  (t) => [
    index("alerts_property_idx").on(t.propertyId),
    index("alerts_severity_idx").on(t.severity),
  ]
);

// An incident is a larger, tracked operational issue (often spanning multiple
// alerts) that someone is actively working to resolve.
export const incidents = pgTable(
  "incidents",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The affected property. Nullable here (no notNull) — an incident may be
    // company-wide and not tied to one site; still cascades if the property goes.
    propertyId: uuid("property_id").references(() => properties.id, {
      onDelete: "cascade",
    }),
    // Short title (required).
    title: text("title").notNull(),
    // Longer narrative summary (optional).
    summary: text("summary"),
    // Lifecycle state; new incidents start "open".
    status: incidentStatus("status").notNull().default("open"),
    // Severity, reusing the alert severity enum; defaults to "warning".
    severity: alertSeverity("severity").notNull().default("warning"),
    // The alert this incident was created from, when applicable. SET NULL on
    // alert deletion so the incident survives its source alert.
    alertId: uuid("alert_id").references(() => alerts.id, { onDelete: "set null" }),
    // Problem category (same vocabulary as alerts.category, e.g. "guest_wifi")
    // — lets automation match "is there already an open incident for this?".
    category: text("category"),
    // Who is working it (free text until RBAC lands: a name, team, or vendor).
    owner: text("owner"),
    // SLA deadline computed from severity at creation; past-due open incidents
    // are auto-escalated by the ticketing automation.
    slaDueAt: timestamp("sla_due_at", { withTimezone: true }),
    // When the incident was opened; auto-set to now on insert.
    openedAt: timestamp("opened_at", { withTimezone: true }).notNull().defaultNow(),
    // When it was resolved; stays NULL while still open.
    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  },
  // Index for fast "all incidents for a property" lookups.
  (t) => [index("incidents_property_idx").on(t.propertyId)]
);

// Free-form work-log entries attached to an incident (who did/found what, when).
export const incidentNotes = pgTable(
  "incident_notes",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The incident this note belongs to; notes vanish with the incident.
    incidentId: uuid("incident_id")
      .notNull()
      .references(() => incidents.id, { onDelete: "cascade" }),
    // Who wrote it (free text until RBAC lands; automation writes "automation").
    author: text("author").notNull().default("ops"),
    // The note body (required).
    body: text("body").notNull(),
    // When the note was added; auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("incident_notes_incident_idx").on(t.incidentId)]
);

// ---------------------------------------------------------------------------
// Vendor / project tracking
// ---------------------------------------------------------------------------

// A vendor here is a business partner/supplier a company works with (an ISP, a
// managed-service provider, a hardware reseller) — not the equipment-vendor enum.
export const vendors = pgTable(
  "vendors",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // Owning company; deletes cascade with the company.
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    // Vendor/company name (required).
    name: text("name").notNull(),
    category: text("category"), // MSP, ISP/telecom, hardware, etc.
    // Primary contact person's name (optional).
    contactName: text("contact_name"),
    // Contact email (optional).
    contactEmail: text("contact_email"),
    // Contact phone number (optional).
    contactPhone: text("contact_phone"),
    // Who to escalate to for urgent issues (optional).
    escalationContact: text("escalation_contact"),
    // Contract window with this vendor (nullable until recorded). The UI flags
    // contracts ending within 90 days so renewals don't sneak up.
    contractStart: timestamp("contract_start", { withTimezone: true }),
    contractEnd: timestamp("contract_end", { withTimezone: true }),
    // Agreed SLA terms in plain text, e.g. "P1 response 15min · 99.9% uptime".
    slaTerms: text("sla_terms"),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index for fast "all vendors for a company" lookups.
  (t) => [index("vendors_company_idx").on(t.companyId)]
);

// A project is a piece of tracked work (a rollout, an install, an upgrade),
// optionally tied to a specific property and/or an external vendor.
export const projects = pgTable(
  "projects",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // Owning company (required); deletes cascade with the company.
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    // Optional related property. `set null` keeps the project but clears the
    // link if that property is deleted.
    propertyId: uuid("property_id").references(() => properties.id, {
      onDelete: "set null",
    }),
    // Optional vendor doing the work; link clears to NULL if the vendor is removed.
    vendorId: uuid("vendor_id").references(() => vendors.id, { onDelete: "set null" }),
    // Project name (required).
    name: text("name").notNull(),
    // Longer description (optional).
    description: text("description"),
    // Lifecycle stage; new projects start in "planning".
    status: projectStatus("status").notNull().default("planning"),
    // Target completion date (optional).
    dueDate: timestamp("due_date", { withTimezone: true }),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  // Index for fast "all projects for a company" lookups.
  (t) => [index("projects_company_idx").on(t.companyId)]
);

// A telecom circuit (DIA, broadband, MPLS, LTE backup…) serving a property,
// usually provided by a carrier vendor. The circuit inventory is how outages
// and contract renewals get tracked per site.
export const circuits = pgTable(
  "circuits",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The property this circuit serves; removed with the property.
    propertyId: uuid("property_id")
      .notNull()
      .references(() => properties.id, { onDelete: "cascade" }),
    // The carrier/vendor providing it; link clears if the vendor is removed.
    vendorId: uuid("vendor_id").references(() => vendors.id, { onDelete: "set null" }),
    // The provider's circuit identifier (what you quote when calling the NOC).
    circuitRef: text("circuit_ref").notNull(),
    // Circuit type, e.g. "DIA fiber", "Cable broadband", "LTE backup".
    type: text("type"),
    // Provisioned bandwidth in Mbps (download, for asymmetric services).
    bandwidthMbps: integer("bandwidth_mbps"),
    // Operational state, reusing the device status enum.
    status: deviceStatus("status").notNull().default("online"),
    // Monthly recurring cost in whole dollars (optional).
    monthlyCost: integer("monthly_cost"),
    // When the circuit contract ends — drives renewal warnings.
    contractEnd: timestamp("contract_end", { withTimezone: true }),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("circuits_property_idx").on(t.propertyId)]
);

// A dated milestone inside a project (e.g. "Site survey", "Hardware staged").
export const projectMilestones = pgTable(
  "project_milestones",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The owning project; milestones vanish with the project.
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    // What the milestone is (required).
    name: text("name").notNull(),
    // Target date (optional).
    dueDate: timestamp("due_date", { withTimezone: true }),
    // When it was completed; NULL while still pending.
    completedAt: timestamp("completed_at", { withTimezone: true }),
    // Display order within the project.
    sortOrder: integer("sort_order").notNull().default(0),
  },
  (t) => [index("project_milestones_project_idx").on(t.projectId)]
);

// One checkbox on a project's go-live list. `phase` separates the cutover
// checklist (work done during the change) from post-deployment validation
// (proof the change worked).
export const projectChecklist = pgTable(
  "project_checklist",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The owning project; items vanish with the project.
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    // Which phase the item belongs to: "cutover" or "validation".
    phase: text("phase").notNull().default("cutover"),
    // The checklist item text (required).
    label: text("label").notNull(),
    // 1 = checked off, 0 = still to do (integer flag convention).
    done: integer("done").notNull().default(0),
    // Display order within the phase.
    sortOrder: integer("sort_order").notNull().default(0),
  },
  (t) => [index("project_checklist_project_idx").on(t.projectId)]
);

// ---------------------------------------------------------------------------
// Security: memberships (RBAC) + audit log
// ---------------------------------------------------------------------------

// Links an authenticated user (Clerk user id) to a company with a role and an
// optional property allow-list — the backbone of company isolation and
// property-level permissions.
export const memberships = pgTable(
  "memberships",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // The auth provider's user id (Clerk). Unique: one membership per user.
    userId: text("user_id").notNull().unique(),
    // Email at the time of enrollment, for display in admin views.
    email: text("email"),
    // The company this user belongs to — company isolation boundary.
    companyId: uuid("company_id")
      .notNull()
      .references(() => companies.id, { onDelete: "cascade" }),
    // The user's role (drives the permission matrix in lib/authz.ts).
    role: memberRole("role").notNull().default("readonly_exec"),
    // Property-level scope: NULL = all properties; otherwise an explicit
    // allow-list of property ids stored as a JSON array.
    propertyIds: jsonb("property_ids").$type<string[] | null>(),
    // Row creation timestamp, auto-set on insert.
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("memberships_company_idx").on(t.companyId)]
);

// Append-only audit trail: who did what, when, to which record — covers
// change history (details carries before/after) and login activity (auth.*
// events from the Clerk webhook). Deliberately has NO foreign keys so history
// survives demo reseeds and record deletions.
export const auditLog = pgTable(
  "audit_log",
  {
    // Primary key, auto-generated UUID.
    id: uuid("id").defaultRandom().primaryKey(),
    // When it happened, auto-set on insert.
    at: timestamp("at", { withTimezone: true }).notNull().defaultNow(),
    // Who: the actor's user id ("dev", "admin-token", or a Clerk user id)…
    actorId: text("actor_id").notNull(),
    // …their display name/email, and role at the time of the action.
    actorName: text("actor_name"),
    role: text("role"),
    // What: a dotted action name, e.g. "incident.update" or "auth.login".
    action: text("action").notNull(),
    // The affected record, e.g. "incident:<uuid>" (nullable for system events).
    target: text("target"),
    // Structured change detail, e.g. {"status":{"from":"open","to":"resolved"}}.
    details: jsonb("details").$type<Record<string, unknown>>(),
  },
  (t) => [index("audit_log_at_idx").on(t.at)]
);

// ---------------------------------------------------------------------------
// Inferred types — shared by mock data, queries, and UI.
// ---------------------------------------------------------------------------

// `$inferSelect` asks Drizzle to derive the TypeScript shape of a row as it
// comes back from a SELECT. We export one type per table so the rest of the app
// (mock data, queries, UI) can refer to a strongly-typed row and never drift
// from the actual columns above.
export type Company = typeof companies.$inferSelect;
export type Property = typeof properties.$inferSelect;
export type Integration = typeof integrations.$inferSelect;
export type SyncRun = typeof syncRuns.$inferSelect;
export type AccessPoint = typeof accessPoints.$inferSelect;
export type Client = typeof clients.$inferSelect;
export type IotDevice = typeof iotDevices.$inferSelect;
export type Alert = typeof alerts.$inferSelect;
export type Incident = typeof incidents.$inferSelect;
export type IncidentNote = typeof incidentNotes.$inferSelect;
export type Vendor = typeof vendors.$inferSelect;
export type Project = typeof projects.$inferSelect;
export type Circuit = typeof circuits.$inferSelect;
export type Membership = typeof memberships.$inferSelect;
export type AuditEntry = typeof auditLog.$inferSelect;
export type ProjectMilestone = typeof projectMilestones.$inferSelect;
export type ProjectChecklistItem = typeof projectChecklist.$inferSelect;

// These derive a union of the allowed enum strings. `.enumValues` is the array
// of values; `[number]` indexes it by any number, which in TypeScript yields the
// union of all element types — e.g. Severity = "critical" | "warning" | "info".
export type Severity = (typeof alertSeverity.enumValues)[number];
export type DeviceState = (typeof deviceStatus.enumValues)[number];
export type Risk = (typeof riskLevel.enumValues)[number];
export type IntegrationVendorName = (typeof integrationVendor.enumValues)[number];
