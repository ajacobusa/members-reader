// Clerk's hosted sign-in component, mounted as a catch-all route (Clerk's
// recommended pattern). With Clerk unconfigured (dev mode) the page explains
// why it's inert instead of crashing without a provider.
import { SignIn } from "@clerk/nextjs";

const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default function SignInPage() {
  if (!hasClerk) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-sm text-muted">
        Authentication is disabled (dev mode). Add Clerk keys to enable sign-in.
      </div>
    );
  }
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <SignIn />
    </div>
  );
}
