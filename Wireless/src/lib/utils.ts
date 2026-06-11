// `clsx` builds a className string from many inputs (strings, arrays, objects).
// `ClassValue` is the type of any single thing clsx accepts; we re-export the type only.
import { clsx, type ClassValue } from "clsx";
// `twMerge` resolves conflicting Tailwind utility classes (e.g. "p-2 p-4" -> "p-4").
import { twMerge } from "tailwind-merge";

/** Tailwind-aware className combiner. */
// Takes any number of class inputs (the `...inputs` rest param collects them into an array).
export function cn(...inputs: ClassValue[]) {
  // First clsx flattens/filters the inputs into one string, then twMerge de-dupes Tailwind conflicts.
  return twMerge(clsx(inputs));
}

/** Relative "x ago" formatting without pulling a heavy dep. */
// Accepts a Date, an ISO string, or nothing (null/undefined) and returns a short human label.
export function timeAgo(date: Date | string | null | undefined): string {
  // No date given: show an em-dash placeholder instead of crashing.
  if (!date) return "—";
  // Normalize to a real Date object: if it's a string, parse it; otherwise use it as-is.
  const t = typeof date === "string" ? new Date(date) : date;
  // How many whole seconds between now and the given time. getTime() is epoch-ms; /1000 -> seconds.
  const seconds = Math.floor((Date.now() - t.getTime()) / 1000);
  // Under a minute old: just say "just now".
  if (seconds < 60) return "just now";
  // Convert seconds to whole minutes.
  const mins = Math.floor(seconds / 60);
  // Under an hour: show minutes, e.g. "12m ago".
  if (mins < 60) return `${mins}m ago`;
  // Convert minutes to whole hours.
  const hours = Math.floor(mins / 60);
  // Under a day: show hours, e.g. "5h ago".
  if (hours < 24) return `${hours}h ago`;
  // A day or more: collapse to whole days.
  const days = Math.floor(hours / 24);
  // Fall through to a day-based label, e.g. "3d ago".
  return `${days}d ago`;
}

// Turns a device's accumulated uptime (in seconds) into a simple 0-100 percentage.
export function uptimePct(seconds: number): number {
  // Treat 30 days as the reference window for a simple uptime %.
  // 30 days * 24 hours * 3600 seconds = total seconds in the reference window.
  const window = 30 * 24 * 3600;
  // uptime/window gives a fraction; *100 makes it a percent; round it, and cap at 100 so we never exceed full.
  return Math.min(100, Math.round((seconds / window) * 100));
}
