import { NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "node:crypto";
import { recordSystemAudit } from "@/lib/audit";

/**
 * Clerk webhook → login-activity capture.
 *
 * Point a Clerk webhook (events: session.created, session.ended, user.created)
 * at POST /api/webhooks/clerk and set CLERK_WEBHOOK_SECRET. Each event lands in
 * the audit log as auth.login / auth.logout / auth.user_created, giving the
 * security page a login-activity trail.
 *
 * Signature verification implements the Svix scheme Clerk uses
 * (HMAC-SHA256 over "id.timestamp.payload" with the whsec_ base64 key) with
 * node:crypto — no extra dependency. Without the secret the endpoint is inert.
 */
export async function POST(req: Request) {
  const secret = process.env.CLERK_WEBHOOK_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "webhook not configured" }, { status: 503 });
  }

  // Svix headers carry the message id, timestamp, and one or more signatures.
  const id = req.headers.get("svix-id") ?? "";
  const timestamp = req.headers.get("svix-timestamp") ?? "";
  const sigHeader = req.headers.get("svix-signature") ?? "";
  const payload = await req.text();
  if (!id || !timestamp || !sigHeader) {
    return NextResponse.json({ error: "missing signature headers" }, { status: 400 });
  }

  // Compute the expected signature: HMAC-SHA256("id.timestamp.payload").
  const key = Buffer.from(secret.replace(/^whsec_/, ""), "base64");
  const expected = createHmac("sha256", key)
    .update(`${id}.${timestamp}.${payload}`)
    .digest("base64");
  // The header lists signatures as "v1,<base64> v1,<base64> …"; accept any match.
  const valid = sigHeader.split(" ").some((part) => {
    const sig = part.split(",")[1] ?? "";
    const a = Buffer.from(sig);
    const b = Buffer.from(expected);
    return a.length === b.length && timingSafeEqual(a, b);
  });
  if (!valid) {
    return NextResponse.json({ error: "invalid signature" }, { status: 401 });
  }

  // Map Clerk events onto audit actions (ignore everything else).
  const event = JSON.parse(payload) as { type?: string; data?: { user_id?: string; id?: string } };
  const userId = event.data?.user_id ?? event.data?.id ?? "unknown";
  const map: Record<string, string> = {
    "session.created": "auth.login",
    "session.ended": "auth.logout",
    "user.created": "auth.user_created",
  };
  const action = map[event.type ?? ""];
  if (action) {
    await recordSystemAudit(userId, action, undefined, { event: event.type });
  }
  return NextResponse.json({ ok: true });
}
