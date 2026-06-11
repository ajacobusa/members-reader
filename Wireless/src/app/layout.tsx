// `Metadata` is a TypeScript type describing the page's <head> info (title, description).
import type { Metadata } from "next";
// Two Google fonts that Next.js will download and self-host for us.
import { Geist, Geist_Mono } from "next/font/google";
// `ClerkProvider` makes Clerk's authentication available to the whole app.
import { ClerkProvider } from "@clerk/nextjs";
// Global CSS (Tailwind base styles, custom variables) applied to every page.
import "./globals.css";

// Load the main sans-serif font and expose it as a CSS variable we can reference in styles.
const geistSans = Geist({
  variable: "--font-geist-sans",
  // Only load the Latin character set to keep the download small.
  subsets: ["latin"],
});

// Load the monospace font (used for code-like text) as its own CSS variable.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// `metadata` is exported so Next.js can put this title/description in the page <head>.
export const metadata: Metadata = {
  title: "Wireless Ops — Hotel WiFi & IoT Management",
  description:
    "Manage hotel WiFi, IoT, alerts, vendors, and property health across your portfolio.",
};

// Auth is opt-in: wrap with ClerkProvider only when keys are configured, so the
// app boots with zero config in development.
// True if a Clerk publishable key is present in the environment, false otherwise.
const hasClerk = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

// The root layout wraps EVERY page in the app. `children` is whatever page is being shown.
// `Readonly<{...}>` just means the props object should not be mutated.
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Build the base HTML document once and store it in `tree`.
  const tree = (
    // The top-level <html> tag. `lang="en"` helps screen readers and SEO.
    // The className attaches our font variables plus full-height and font-smoothing styles.
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* The <body> holds the actual page content passed in as `children`. */}
      <body className="min-h-full">{children}</body>
    </html>
  );

  // If Clerk is set up, wrap the document in ClerkProvider so auth works everywhere.
  // Otherwise return the plain document so the app still runs without auth keys.
  return hasClerk ? <ClerkProvider>{tree}</ClerkProvider> : tree;
}
