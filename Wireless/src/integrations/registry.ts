// The union of valid vendor id strings, shared with the DB schema.
import type { IntegrationVendorName } from "@/db/schema";
// The interface every adapter implements, plus the credentials bag we pass in.
import type { VendorAdapter, VendorCredentials } from "./types";
// Bring in each concrete adapter class so we can construct it on demand below.
import { ArubaCentralAdapter } from "./aruba";
import { MerakiAdapter } from "./meraki";
import { UniFiAdapter } from "./unifi";
import { RuckusAdapter } from "./ruckus";
import { FortinetAdapter } from "./fortinet";
import { MistAdapter } from "./mist";

/**
 * Vendor adapter registry. Adding a manufacturer is one line here plus a new
 * adapter class — nothing else in the platform changes.
 */
// A "factory" is just a function that takes optional credentials and hands back
// a ready-to-use adapter instance. Storing functions (not instances) lets us
// build an adapter lazily, only when it's actually requested.
type AdapterFactory = (creds?: VendorCredentials) => VendorAdapter;

// The lookup table mapping each vendor id to its factory function.
// `Partial<Record<...>>` means: keys come from IntegrationVendorName, but not
// every vendor has to be present (some may not be wired up yet).
const REGISTRY: Partial<Record<IntegrationVendorName, AdapterFactory>> = {
  // Each entry: when asked for this vendor, build the matching adapter with creds.
  aruba_central: (creds) => new ArubaCentralAdapter(creds),
  meraki: (creds) => new MerakiAdapter(creds),
  unifi: (creds) => new UniFiAdapter(creds),
  ruckus: (creds) => new RuckusAdapter(creds),
  fortinet: (creds) => new FortinetAdapter(creds),
  mist: (creds) => new MistAdapter(creds),
};

// The main entry point: given a vendor id (and optional creds), return a live
// adapter object. This is what the rest of the app calls instead of `new`-ing
// vendor classes directly, so callers stay vendor-agnostic.
export function getAdapter(
  vendor: IntegrationVendorName,
  creds?: VendorCredentials
): VendorAdapter {
  // Look up the factory for this vendor in the registry table.
  const factory = REGISTRY[vendor];
  // If no factory exists, this vendor isn't supported yet — fail loudly.
  if (!factory) {
    throw new Error(`No adapter registered for vendor "${vendor}" yet.`);
  }
  // Run the factory to build and return the adapter instance.
  return factory(creds);
}

// Helper that lists every vendor id currently registered (e.g. to populate a
// dropdown of supported integrations).
export function supportedVendors(): IntegrationVendorName[] {
  // Object.keys gives string[]; we assert it as the more specific vendor type
  // since we know the keys all came from IntegrationVendorName.
  return Object.keys(REGISTRY) as IntegrationVendorName[];
}
