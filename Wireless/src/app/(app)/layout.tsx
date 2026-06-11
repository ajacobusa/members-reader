// Clerk's pre-built avatar/menu button for the signed-in user.
import { UserButton } from "@clerk/nextjs";
// Our own left-hand navigation sidebar component.
import { Sidebar } from "@/components/sidebar";

/**
 * Authenticated app shell: sidebar + topbar around every dashboard page.
 * When Clerk is configured, the topbar shows the user button; otherwise a
 * "dev mode" badge, so the shell renders identically with or without auth.
 */
// True when Clerk keys exist, so we can decide what to show in the topbar.
const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

// Render every dashboard page per-request instead of prerendering at build
// time. Required once a real database is connected: live alerts/health must
// reflect the data at view time, not a snapshot baked into the build.
export const dynamic = "force-dynamic";

// This layout wraps every page inside the (app) route group with a shared shell.
// `children` is the specific dashboard page being viewed.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    // Full-height flex row: sidebar on the left, main content on the right.
    // `overflow-hidden` keeps the outer box from scrolling; inner areas scroll instead.
    <div className="flex h-screen overflow-hidden">
      {/* The left navigation sidebar (links to Dashboard, Properties, etc.). */}
      <Sidebar />
      {/* Right column: takes the remaining width and stacks topbar + content vertically. */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* The top bar: fixed height, a label on the left and user controls on the right. */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-6">
          {/* Small descriptive label shown on the left of the topbar. */}
          <div className="text-sm text-muted">Portfolio operations console</div>
          {/* Right side of the topbar holds the auth control. */}
          <div className="flex items-center gap-3">
            {/* If Clerk is on, show the real user button; if off, show a dev-mode badge. */}
            {hasClerk ? (
              <UserButton />
            ) : (
              <span className="rounded-full bg-surface-2 px-3 py-1 text-xs text-muted">
                Dev mode · auth off · acting as Owner
              </span>
            )}
          </div>
        </header>
        {/* The main scrollable area where each page's content is rendered. */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
