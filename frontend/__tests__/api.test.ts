import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getWsUrl } from "@/lib/api";

// Mock window.location
const mockLocation = { href: "", pathname: "/" };
Object.defineProperty(window, "location", {
  value: mockLocation,
  writable: true,
});

describe("API client", () => {
  beforeEach(() => {
    mockLocation.href = "";
    mockLocation.pathname = "/";
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("makes GET request with correct URL", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ balance_cents: 5000 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    // Dynamic import to get fresh module
    const { fetchDashboard } = await import("@/lib/api");
    await fetchDashboard();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/dashboard"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      })
    );
  });

  it("redirects to /onboarding on 401", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Not authenticated" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { fetchDashboard } = await import("@/lib/api");

    await expect(fetchDashboard()).rejects.toThrow();
    expect(mockLocation.href).toBe("/onboarding");
  });

  it("extracts error message from response", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: "Custom error message" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { fetchDashboard } = await import("@/lib/api");

    await expect(fetchDashboard()).rejects.toThrow("Custom error message");
  });

  it("handles 204 No Content", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    });
    vi.stubGlobal("fetch", mockFetch);

    const { disconnect } = await import("@/lib/api");
    const result = await disconnect();

    expect(result).toBeUndefined();
  });

  it("sends POST with JSON body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ valid: true, balance_cents: 5000 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { validateCredentials } = await import("@/lib/api");
    await validateCredentials({
      key_id: "test-key",
      private_key: "test-pem",
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/validate"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          key_id: "test-key",
          private_key: "test-pem",
        }),
      })
    );
  });

  it("builds query params for trades", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ trades: [], total: 0, page: 1 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { fetchTrades } = await import("@/lib/api");
    await fetchTrades(2, "NYC", "WON");

    const calledUrl = mockFetch.mock.calls[0][0];
    expect(calledUrl).toContain("page=2");
    expect(calledUrl).toContain("city=NYC");
    expect(calledUrl).toContain("status=WON");
  });

  it("handles network errors gracefully", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network failure"));
    vi.stubGlobal("fetch", mockFetch);

    const { fetchDashboard } = await import("@/lib/api");
    await expect(fetchDashboard()).rejects.toThrow("Network failure");
  });
});

describe("getWsUrl", () => {
  it("converts http to ws and appends /ws", () => {
    // Default API_URL is http://localhost:8000
    expect(getWsUrl()).toBe("ws://localhost:8000/ws");
  });

  it("returns a URL ending with /ws", () => {
    expect(getWsUrl()).toMatch(/\/ws$/);
  });

  it("starts with ws:// protocol", () => {
    expect(getWsUrl()).toMatch(/^ws:\/\//);
  });
});
