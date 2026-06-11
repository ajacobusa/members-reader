// "use client" marks this as a Client Component: it runs in the browser, which is
// required because it uses a hook (usePathname) that reads the current URL.
"use client";

// Next.js's <Link> gives fast client-side navigation between pages (no full reload).
import Link from "next/link";
// `usePathname` is a hook that returns the current URL path (e.g. "/devices").
import { usePathname } from "next/navigation";
// Icon components from the lucide-react icon library, one per nav item.
import {
  LayoutDashboard,
  Building2,
  Router,
  Bell,
  Wrench,
  Plug,
  Wifi,
  ShieldCheck,
  ClipboardList,
  ScrollText,
} from "lucide-react";
// `cn` is a small helper that joins CSS class names together (and handles conditionals).
import { cn } from "@/lib/utils";

// The list of navigation links. Keeping it as data makes it easy to add/remove items.
// Each entry has the URL (href), the visible text (label), and its icon component.
const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/properties", label: "Properties", icon: Building2 },
  { href: "/devices", label: "Device Inventory", icon: Router },
  { href: "/iot", label: "IoT Security", icon: ShieldCheck },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/incidents", label: "Incidents", icon: ClipboardList },
  { href: "/vendors", label: "Vendors & Projects", icon: Wrench },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/audit", label: "Security & Audit", icon: ScrollText },
];

// The Sidebar component renders the left navigation column.
export function Sidebar() {
  // Read which page we're currently on so we can highlight the matching link.
  const pathname = usePathname();
  return (
    // <aside> is the semantic tag for sidebar content; fixed width, vertical layout.
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface">
      {/* Brand block at the top: logo square plus app name and subtitle. */}
      <div className="flex items-center gap-2 px-5 py-4">
        {/* Colored square that holds the WiFi logo icon. */}
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-fg">
          <Wifi className="h-5 w-5" />
        </div>
        {/* App name and the company subtitle, stacked tightly. */}
        <div className="leading-tight">
          <div className="text-sm font-semibold">Wireless Ops</div>
          <div className="text-xs text-muted">Coastline Hospitality</div>
        </div>
      </div>
      {/* The navigation list. `flex-1` makes it grow to fill the space above the footer. */}
      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {/* Loop over each NAV entry and turn it into a clickable link. */}
        {/* We rename the entry's `icon` to `Icon` (capitalized) so JSX treats it as a component. */}
        {NAV.map(({ href, label, icon: Icon }) => {
          // A link is "active" if the URL exactly matches it, OR (for non-dashboard
          // links) if the current path starts with the link's href (a sub-page).
          const active =
            pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
          return (
            // One navigation link. `key` helps React track list items efficiently.
            // The className below applies base styles always, then picks active vs
            // inactive styling based on the `active` flag computed above.
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-surface-2 text-foreground"
                  : "text-muted hover:bg-surface-2 hover:text-foreground"
              )}
            >
              {/* The link's icon, followed by its text label. */}
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      {/* Footer pinned at the bottom showing the build stage and vendor. */}
      <div className="border-t border-border px-5 py-3 text-xs text-muted">
        MVP · Aruba Central
      </div>
    </aside>
  );
}
