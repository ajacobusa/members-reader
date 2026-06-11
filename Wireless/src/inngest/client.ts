// Bring in the `Inngest` class from the "inngest" package (installed via npm).
// Inngest is a service for running background/queued jobs reliably.
import { Inngest } from "inngest";

/** Inngest client — durable background jobs (vendor syncs, analytics, reports). */
// Create one shared Inngest "client" for the whole app and export it so other
// files can import and reuse it. The `id` ("wireless-ops") is a unique name for
// this app inside Inngest — it groups and identifies all our jobs.
export const inngest = new Inngest({ id: "wireless-ops" });
