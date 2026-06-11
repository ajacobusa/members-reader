import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Auth middleware.
 *
 * Clerk is enforced only when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is set:
 *  - With it, every app page requires sign-in (auth.protect redirects to
 *    /sign-in) EXCEPT the public/machine routes below.
 *  - Without it (default dev/demo), the dashboard is open so the app runs
 *    with zero config.
 */
const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

// Routes that must work without a Clerk session:
//  - sign-in/sign-up pages themselves,
//  - machine endpoints with their own auth (admin bearer token, Inngest
//    signing, Clerk webhook signature).
const isPublicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/admin(.*)",
  "/api/inngest(.*)",
  "/api/webhooks(.*)",
]);

export default hasClerk
  ? clerkMiddleware(async (auth, req) => {
      // Everything that isn't explicitly public requires a signed-in user.
      if (!isPublicRoute(req)) await auth.protect();
    })
  : () => NextResponse.next();

export const config = {
  matcher: [
    // Skip Next internals and static files.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run on API routes.
    "/(api|trpc)(.*)",
  ],
};
