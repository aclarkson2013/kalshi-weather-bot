import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the api module
vi.mock("@/lib/api", () => ({
  fetchDashboard: vi.fn(),
  fetchMarkets: vi.fn(),
  fetchPendingTrades: vi.fn(),
  fetchTrades: vi.fn(),
  fetchSettings: vi.fn(),
  fetchLogs: vi.fn(),
  fetchPerformance: vi.fn(),
}));

// Mock SWR to test hook configuration
vi.mock("swr", () => {
  const actual = vi.importActual("swr");
  return {
    ...actual,
    default: vi.fn((key: string, fetcher: () => unknown, config: Record<string, unknown>) => ({
      data: undefined,
      error: undefined,
      isLoading: true,
      mutate: vi.fn(),
      // Expose config for testing
      _key: key,
      _config: config,
    })),
  };
});

describe("SWR hooks configuration", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("useDashboard has 30s refresh interval", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { useDashboard } = await import("@/lib/hooks");

    useDashboard();

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/dashboard");
    expect(call[2].refreshInterval).toBe(30000);
  });

  it("useMarkets has 60s refresh interval", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { useMarkets } = await import("@/lib/hooks");

    useMarkets();

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/markets");
    expect(call[2].refreshInterval).toBe(60000);
  });

  it("useMarkets passes city filter in key", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { useMarkets } = await import("@/lib/hooks");

    useMarkets("NYC");

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/markets?city=NYC");
  });

  it("usePendingTrades has 10s refresh interval", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { usePendingTrades } = await import("@/lib/hooks");

    usePendingTrades();

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/queue");
    expect(call[2].refreshInterval).toBe(10000);
  });

  it("useLogs has 2s refresh interval", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { useLogs } = await import("@/lib/hooks");

    useLogs();

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/logs");
    expect(call[2].refreshInterval).toBe(2000);
  });

  it("useTrades has no refresh", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { useTrades } = await import("@/lib/hooks");

    useTrades(1);

    const call = useSWR.mock.calls[0];
    expect(call[2].refreshInterval).toBe(0);
  });

  it("useSettings has no refresh", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { useSettings } = await import("@/lib/hooks");

    useSettings();

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/settings");
    expect(call[2].refreshInterval).toBe(0);
  });

  it("usePerformance has no refresh", async () => {
    const useSWR = (await import("swr")).default as unknown as ReturnType<typeof vi.fn>;
    const { usePerformance } = await import("@/lib/hooks");

    usePerformance();

    const call = useSWR.mock.calls[0];
    expect(call[0]).toBe("/api/performance");
    expect(call[2].refreshInterval).toBe(0);
  });
});
