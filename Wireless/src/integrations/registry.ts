import type { IntegrationVendorName } from "@/db/schema";
import type { VendorAdapter, VendorCredentials } from "./types";
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
type AdapterFactory = (creds?: VendorCredentials) => VendorAdapter;

const REGISTRY: Partial<Record<IntegrationVendorName, AdapterFactory>> = {
  aruba_central: (creds) => new ArubaCentralAdapter(creds),
  meraki: (creds) => new MerakiAdapter(creds),
  unifi: (creds) => new UniFiAdapter(creds),
  ruckus: (creds) => new RuckusAdapter(creds),
  fortinet: (creds) => new FortinetAdapter(creds),
  mist: (creds) => new MistAdapter(creds),
};

export function getAdapter(
  vendor: IntegrationVendorName,
  creds?: VendorCredentials
): VendorAdapter {
  const factory = REGISTRY[vendor];
  if (!factory) {
    throw new Error(`No adapter registered for vendor "${vendor}" yet.`);
  }
  return factory(creds);
}

export function supportedVendors(): IntegrationVendorName[] {
  return Object.keys(REGISTRY) as IntegrationVendorName[];
}
