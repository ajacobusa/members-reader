// NOTE: no "server-only" marker here — the pure parts (ROLES, can,
// visibleProperties) are also imported by the verification script. Everything
// touching the database or Clerk stays inside async functions that only run
// on the server.
import { eq } from "drizzle-orm";
import { getDb, hasDatabase, schema } from "@/db/client";
import type { Property } from "@/db/schema";

/**
 * Authorization core — roles, the permission matrix, and actor resolution.
 *
 * Three layers of access control:
 *  1. ROLE → ACTION matrix (can): what each role may do.
 *  2. Company isolation: an actor belongs to one company (memberships table);
 *     all data access happens within it.
 *  3. Property-level permissions: a membership may list specific property ids;
 *     null means "all properties in the company" (visibleProperties filters).
 *
 * Modes:
 *  - Clerk OFF (no NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY): dev mode — everyone is
 *    a full-access Owner so the demo stays public and writable.
 *  - Clerk ON: the signed-in user's membership row decides role + scope. The
 *    very first signed-in user bootstraps as Owner; later users without a
 *    membership get read-only access to nothing until an admin adds them.
 */

// The six platform roles, from the product spec.
export const ROLES = [
  "owner",
  "admin",
  "network_engineer",
  "property_manager",
  "vendor_msp",
  "readonly_exec",
] as const;
export type Role = (typeof ROLES)[number];

// Every permission-gated action in the app.
export const ACTIONS = [
  "view", // read dashboards and inventories
  "incident.create", // open incidents from alerts
  "incident.update", // assign owner / change status
  "incident.note", // add work-log notes
  "project.toggle", // milestones + cutover/validation checkboxes
  "integration.manage", // store vendor credentials, trigger syncs
  "admin.maintenance", // db setup / reseed
  "ai.run", // generate AI summaries/reports
] as const;
export type Action = (typeof ACTIONS)[number];

// The matrix: which actions each role may perform. Single source of truth —
// the audit page renders this table directly so docs can't drift from code.
const MATRIX: Record<Role, readonly Action[]> = {
  owner: ACTIONS,
  admin: ACTIONS,
  network_engineer: [
    "view",
    "incident.create",
    "incident.update",
    "incident.note",
    "project.toggle",
    "ai.run",
  ],
  property_manager: ["view", "incident.create", "incident.note", "ai.run"],
  vendor_msp: ["view", "incident.update", "incident.note"],
  readonly_exec: ["view", "ai.run"],
};

/** Pure permission check: may `role` perform `action`? */
export function can(role: Role, action: Action): boolean {
  return MATRIX[role]?.includes(action) ?? false;
}

/** Expose the matrix (read-only) for the audit page's access-model table. */
export function permissionMatrix(): Record<Role, readonly Action[]> {
  return MATRIX;
}

// The resolved identity making the current request.
export interface Actor {
  userId: string;
  name: string;
  role: Role;
  /** null = every property in the company; otherwise an explicit allow-list. */
  propertyIds: string[] | null;
}

/** Property-level permissions: filter a property list to the actor's scope. */
export function visibleProperties(actor: Actor, all: Property[]): Property[] {
  if (actor.propertyIds === null) return all;
  const allowed = new Set(actor.propertyIds);
  return all.filter((p) => allowed.has(p.id));
}

// Dev-mode actor: full access so the zero-config demo works end to end.
const DEV_ACTOR: Actor = { userId: "dev", name: "Dev Mode", role: "owner", propertyIds: null };

/** Resolve the actor for the current request (Clerk-aware, dev fallback). */
export async function getActor(): Promise<Actor> {
  // Dev mode: no Clerk configured — act as Owner.
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) return DEV_ACTOR;

  // Clerk mode: resolve the signed-in user (import lazily so dev mode never
  // touches Clerk internals).
  const { auth, currentUser } = await import("@clerk/nextjs/server");
  const { userId } = await auth();
  if (!userId) {
    // Middleware redirects unauthenticated users; this is a safety net.
    return { userId: "anonymous", name: "Anonymous", role: "readonly_exec", propertyIds: [] };
  }

  // Without a database there is nowhere to keep memberships — treat any
  // signed-in user as Owner (auth on, RBAC effectively single-user).
  if (!hasDatabase()) {
    return { userId, name: "Signed-in user", role: "owner", propertyIds: null };
  }

  const db = getDb();
  const rows = await db
    .select()
    .from(schema.memberships)
    .where(eq(schema.memberships.userId, userId))
    .limit(1);

  if (rows[0]) {
    return {
      userId,
      name: rows[0].email ?? userId,
      role: rows[0].role,
      propertyIds: rows[0].propertyIds,
    };
  }

  // Bootstrap: the FIRST user to sign in becomes Owner of the company.
  const existing = await db.select({ id: schema.memberships.id }).from(schema.memberships).limit(1);
  const user = await currentUser();
  const email = user?.primaryEmailAddress?.emailAddress ?? null;
  if (existing.length === 0) {
    const company = await db.select({ id: schema.companies.id }).from(schema.companies).limit(1);
    if (company[0]) {
      await db.insert(schema.memberships).values({
        userId,
        email,
        companyId: company[0].id,
        role: "owner",
        propertyIds: null,
      });
      return { userId, name: email ?? userId, role: "owner", propertyIds: null };
    }
  }
  // Company isolation: unknown users see nothing until an admin grants access.
  return { userId, name: email ?? userId, role: "readonly_exec", propertyIds: [] };
}
