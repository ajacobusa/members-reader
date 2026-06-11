import "server-only";
import { timingSafeEqual } from "node:crypto";

/**
 * Shared bearer-token check for the /api/admin/* endpoints.
 * Compares against ADMIN_TASK_TOKEN in constant time; with the env var unset,
 * every admin endpoint is inert (always 401).
 */
export function adminAuthorized(req: Request): boolean {
  const expected = process.env.ADMIN_TASK_TOKEN;
  if (!expected) return false;
  const got = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  const a = Buffer.from(got);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}
