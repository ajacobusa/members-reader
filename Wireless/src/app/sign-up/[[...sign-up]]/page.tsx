// Clerk's hosted sign-up component (catch-all route). Inert in dev mode.
import { SignUp } from "@clerk/nextjs";

const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default function SignUpPage() {
  if (!hasClerk) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-sm text-muted">
        Authentication is disabled (dev mode). Add Clerk keys to enable sign-up.
      </div>
    );
  }
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <SignUp />
    </div>
  );
}
