/**
 * Utility functions for formatting monetary values, probabilities, and dates.
 *
 * All monetary values from the backend are in CENTS (integers).
 * These helpers convert to human-readable dollar strings for display.
 */

import type { CityCode } from "./types";

/** Human-readable city names keyed by CityCode. */
export const CITY_NAMES: Record<CityCode, string> = {
  NYC: "New York",
  CHI: "Chicago",
  MIA: "Miami",
  AUS: "Austin",
};

/**
 * Convert cents (integer) to dollars string: "1.23"
 */
export function centsToDollars(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Format cents as signed P&L: "+$1.23" or "-$0.50"
 */
export function formatPnL(cents: number): string {
  const abs = Math.abs(cents);
  const dollars = (abs / 100).toFixed(2);
  if (cents >= 0) {
    return `+$${dollars}`;
  }
  return `-$${dollars}`;
}

/**
 * Format a decimal probability as a percentage: 0.30 → "30%"
 */
export function formatProbability(prob: number): string {
  return `${Math.round(prob * 100)}%`;
}

/**
 * Format an ISO date string or Date object for display.
 * Returns "Mon, Feb 18" style format.
 */
export function formatDate(dateStr: string | Date): string {
  const d = typeof dateStr === "string" ? new Date(dateStr) : dateStr;
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/**
 * Format an ISO datetime string for display with time.
 * Returns "Feb 18, 2:30 PM" style format.
 */
export function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Calculate time remaining until a target datetime.
 * Returns "2h 15m" or "Expired" if past.
 */
export function timeRemaining(expiresAt: string): string {
  const now = Date.now();
  const target = new Date(expiresAt).getTime();
  const diff = target - now;

  if (diff <= 0) return "Expired";

  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/**
 * Return a Tailwind text color class for a trade status.
 */
export function statusColor(status: string): string {
  switch (status) {
    case "WON":
      return "text-boz-success";
    case "LOST":
      return "text-boz-danger";
    case "OPEN":
      return "text-boz-primary";
    case "CANCELED":
      return "text-boz-neutral";
    default:
      return "text-gray-700";
  }
}

/**
 * Return a Tailwind background color class for a confidence level.
 */
export function confidenceBadgeColor(confidence: string): string {
  switch (confidence) {
    case "high":
      return "bg-green-100 text-green-800";
    case "medium":
      return "bg-yellow-100 text-yellow-800";
    case "low":
      return "bg-red-100 text-red-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}
