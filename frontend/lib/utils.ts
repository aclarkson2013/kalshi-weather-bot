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
 *
 * IMPORTANT: Date-only strings like "2026-02-20" are parsed by JS as UTC midnight.
 * In US timezones this shifts backward to the previous day. We append T12:00:00
 * to force midday parsing so the displayed date matches the intended date.
 */
export function formatDate(dateStr: string | Date): string {
  let d: Date;
  if (typeof dateStr === "string") {
    // Date-only string (YYYY-MM-DD) → add noon to avoid timezone day shift
    d = /^\d{4}-\d{2}-\d{2}$/.test(dateStr)
      ? new Date(dateStr + "T12:00:00")
      : new Date(dateStr);
  } else {
    d = dateStr;
  }
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/**
 * Format an ISO datetime string for display with time in local timezone.
 * Backend stores UTC without "Z" suffix, so we append it to ensure
 * JavaScript properly converts to the user's local time.
 * Returns "Feb 18, 2:30 PM" style format.
 */
export function formatDateTime(dateStr: string): string {
  // If no timezone info, treat as UTC (backend stores naive UTC datetimes)
  const normalized =
    typeof dateStr === "string" && !dateStr.endsWith("Z") && !dateStr.includes("+")
      ? dateStr + "Z"
      : dateStr;
  const d = new Date(normalized);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Format an ISO datetime string to show just the time in local timezone.
 * Backend stores UTC without "Z" suffix, so we append it to ensure
 * JavaScript properly converts to the user's local time.
 * Returns "3:06 PM" style format.
 */
export function formatTime(dateStr: string): string {
  // If no timezone info, treat as UTC (backend stores naive UTC datetimes)
  const normalized =
    typeof dateStr === "string" && !dateStr.endsWith("Z") && !dateStr.includes("+")
      ? dateStr + "Z"
      : dateStr;
  const d = new Date(normalized);
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Calculate trade cost, payout, and potential profit from price and quantity.
 * All values in cents. Payout assumes $1 per contract on the winning side.
 */
export function tradeFinancials(priceCents: number, quantity: number, side: string) {
  // Cost is what you pay: price × quantity for YES, (100 - price) × quantity for NO
  const costCents = side === "yes" ? priceCents * quantity : (100 - priceCents) * quantity;
  // Payout if right: $1.00 × quantity = 100 cents per contract
  const payoutCents = 100 * quantity;
  // Potential profit: payout - cost
  const profitCents = payoutCents - costCents;
  return { costCents, payoutCents, profitCents };
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

// ─── Settlement Date Utilities ───

const MONTH_MAP: Record<string, number> = {
  JAN: 0, FEB: 1, MAR: 2, APR: 3, MAY: 4, JUN: 5,
  JUL: 6, AUG: 7, SEP: 8, OCT: 9, NOV: 10, DEC: 11,
};

/**
 * Parse the event (settlement) date from a Kalshi market ticker.
 *
 * Ticker format: KXHIGH{CITY}-{YY}{MMM}{DD}-{TYPE}{STRIKE}
 * Example: KXHIGHCHI-26FEB21-T35 → Feb 21, 2026
 *
 * Returns null if the ticker is missing or can't be parsed.
 */
export function parseSettlementDate(ticker: string | null | undefined): Date | null {
  if (!ticker) return null;

  // Match the date segment: 2-digit year, 3-letter month, 2-digit day
  const match = ticker.match(/(\d{2})([A-Z]{3})(\d{2})/);
  if (!match) return null;

  const year = 2000 + parseInt(match[1], 10);
  const month = MONTH_MAP[match[2]];
  const day = parseInt(match[3], 10);

  if (month === undefined || isNaN(day)) return null;

  return new Date(year, month, day, 12, 0, 0); // noon to avoid timezone issues
}

/**
 * Return a human-readable settlement countdown string.
 *
 * - "Settles today" if the event date is today
 * - "Settles tomorrow" if the event date is tomorrow
 * - "Settles Fri, Feb 21" for dates further out
 * - "Settling..." if the event date has passed but no settlement yet
 * - null if no ticker/date available
 */
export function settlementCountdown(
  ticker: string | null | undefined,
  isSettled?: boolean,
): string | null {
  if (isSettled) return null; // already settled, no countdown needed

  const eventDate = parseSettlementDate(ticker);
  if (!eventDate) return null;

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const event = new Date(eventDate.getFullYear(), eventDate.getMonth(), eventDate.getDate());

  const diffDays = Math.round((event.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return "Settling...";

  return `Settles ${formatDate(eventDate)}`;
}
