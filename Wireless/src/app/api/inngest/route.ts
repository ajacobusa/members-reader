// `serve` builds the HTTP request handlers Inngest needs, tailored for Next.js.
import { serve } from "inngest/next";
// Our shared Inngest client (knows the app id and how to talk to Inngest).
import { inngest } from "@/inngest/client";
// The list of all job definitions we want this endpoint to expose/run.
import { functions } from "@/inngest/functions";

/** Inngest endpoint. Run `npx inngest-cli dev` locally to drive jobs. */
// Call `serve` with our client and jobs; it returns an object with HTTP method
// handlers. In Next.js App Router, exporting GET/POST/PUT from a route file makes
// this URL respond to those methods. Inngest uses them to discover and run jobs.
export const { GET, POST, PUT } = serve({ client: inngest, functions });
