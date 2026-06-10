import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
import { functions } from "@/inngest/functions";

/** Inngest endpoint. Run `npx inngest-cli dev` locally to drive jobs. */
export const { GET, POST, PUT } = serve({ client: inngest, functions });
