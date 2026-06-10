/**
 * Thrown by an adapter's LIVE-mode methods that aren't wired to the real vendor
 * API yet. The message names the exact call to implement, so the boundary
 * between "works on mock data" and "needs credentials + REST wiring" is explicit.
 */
export class NotImplemented extends Error {
  constructor(vendor: string, what: string) {
    super(
      `${vendor} LIVE mode not wired yet: ${what}. ` +
        `Provide credentials and implement the marked REST call.`
    );
    this.name = "NotImplemented";
  }
}
