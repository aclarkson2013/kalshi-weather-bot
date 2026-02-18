import { describe, expect, it } from "vitest";

import {
  centsToDollars,
  confidenceBadgeColor,
  formatDate,
  formatPnL,
  formatProbability,
  statusColor,
  timeRemaining,
  CITY_NAMES,
} from "@/lib/utils";

describe("centsToDollars", () => {
  it("converts positive cents", () => {
    expect(centsToDollars(150)).toBe("1.50");
  });

  it("converts zero", () => {
    expect(centsToDollars(0)).toBe("0.00");
  });

  it("converts negative cents", () => {
    expect(centsToDollars(-250)).toBe("-2.50");
  });

  it("handles small amounts", () => {
    expect(centsToDollars(1)).toBe("0.01");
  });

  it("handles large amounts", () => {
    expect(centsToDollars(100000)).toBe("1000.00");
  });
});

describe("formatPnL", () => {
  it("formats positive P&L with plus sign", () => {
    expect(formatPnL(500)).toBe("+$5.00");
  });

  it("formats negative P&L with minus sign", () => {
    expect(formatPnL(-250)).toBe("-$2.50");
  });

  it("formats zero as positive", () => {
    expect(formatPnL(0)).toBe("+$0.00");
  });

  it("formats single cent", () => {
    expect(formatPnL(1)).toBe("+$0.01");
  });
});

describe("formatProbability", () => {
  it("formats decimal to percentage", () => {
    expect(formatProbability(0.3)).toBe("30%");
  });

  it("formats 1.0", () => {
    expect(formatProbability(1.0)).toBe("100%");
  });

  it("formats 0.0", () => {
    expect(formatProbability(0)).toBe("0%");
  });

  it("rounds to nearest integer", () => {
    expect(formatProbability(0.155)).toBe("16%");
  });
});

describe("formatDate", () => {
  it("formats ISO date string", () => {
    const result = formatDate("2025-02-18");
    // Output depends on locale, just verify it's a non-empty string
    expect(result).toBeTruthy();
    expect(typeof result).toBe("string");
  });

  it("formats Date object", () => {
    const result = formatDate(new Date(2025, 1, 18)); // Feb 18, 2025
    expect(result).toBeTruthy();
  });
});

describe("statusColor", () => {
  it("returns success color for WON", () => {
    expect(statusColor("WON")).toBe("text-boz-success");
  });

  it("returns danger color for LOST", () => {
    expect(statusColor("LOST")).toBe("text-boz-danger");
  });

  it("returns primary color for OPEN", () => {
    expect(statusColor("OPEN")).toBe("text-boz-primary");
  });

  it("returns neutral for CANCELED", () => {
    expect(statusColor("CANCELED")).toBe("text-boz-neutral");
  });

  it("returns default for unknown", () => {
    expect(statusColor("UNKNOWN")).toBe("text-gray-700");
  });
});

describe("confidenceBadgeColor", () => {
  it("returns green for high", () => {
    expect(confidenceBadgeColor("high")).toContain("green");
  });

  it("returns yellow for medium", () => {
    expect(confidenceBadgeColor("medium")).toContain("yellow");
  });

  it("returns red for low", () => {
    expect(confidenceBadgeColor("low")).toContain("red");
  });
});

describe("timeRemaining", () => {
  it("returns Expired for past dates", () => {
    const past = new Date(Date.now() - 60000).toISOString();
    expect(timeRemaining(past)).toBe("Expired");
  });

  it("returns minutes for near future", () => {
    const future = new Date(Date.now() + 30 * 60000).toISOString();
    const result = timeRemaining(future);
    expect(result).toMatch(/^\d+m$/);
  });

  it("returns hours and minutes for far future", () => {
    const future = new Date(Date.now() + 2 * 3600000 + 15 * 60000).toISOString();
    const result = timeRemaining(future);
    expect(result).toMatch(/^\d+h \d+m$/);
  });
});

describe("CITY_NAMES", () => {
  it("has all four cities", () => {
    expect(CITY_NAMES.NYC).toBe("New York");
    expect(CITY_NAMES.CHI).toBe("Chicago");
    expect(CITY_NAMES.MIA).toBe("Miami");
    expect(CITY_NAMES.AUS).toBe("Austin");
  });
});
