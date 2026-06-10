import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind-aware className combiner. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Relative "x ago" formatting without pulling a heavy dep. */
export function timeAgo(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const t = typeof date === "string" ? new Date(date) : date;
  const seconds = Math.floor((Date.now() - t.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function uptimePct(seconds: number): number {
  // Treat 30 days as the reference window for a simple uptime %.
  const window = 30 * 24 * 3600;
  return Math.min(100, Math.round((seconds / window) * 100));
}
