/**
 * Thrown by an adapter's LIVE-mode methods that aren't wired to the real vendor
 * API yet. The message names the exact call to implement, so the boundary
 * between "works on mock data" and "needs credentials + REST wiring" is explicit.
 */
// A custom error type. Extending the built-in `Error` lets us throw a clear,
// recognizable error (and catch it specifically) when LIVE code isn't ready.
export class NotImplemented extends Error {
  // Takes the vendor's display name and the name of the call that's missing,
  // so the message pinpoints exactly what still needs to be built.
  constructor(vendor: string, what: string) {
    // `super(...)` sets the Error's message. We assemble a helpful sentence
    // naming the vendor, the unfinished method, and the next step to take.
    super(
      `${vendor} LIVE mode not wired yet: ${what}. ` +
        `Provide credentials and implement the marked REST call.`
    );
    // Override the default error name so logs/stack traces read "NotImplemented"
    // instead of the generic "Error".
    this.name = "NotImplemented";
  }
}
