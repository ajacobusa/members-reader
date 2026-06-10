import { UserButton } from "@clerk/nextjs";
import { Sidebar } from "@/components/sidebar";

/**
 * Authenticated app shell: sidebar + topbar around every dashboard page.
 * When Clerk is configured, the topbar shows the user button; otherwise a
 * "dev mode" badge, so the shell renders identically with or without auth.
 */
const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-6">
          <div className="text-sm text-muted">Portfolio operations console</div>
          <div className="flex items-center gap-3">
            {hasClerk ? (
              <UserButton />
            ) : (
              <span className="rounded-full bg-surface-2 px-3 py-1 text-xs text-muted">
                Dev mode · auth off
              </span>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
