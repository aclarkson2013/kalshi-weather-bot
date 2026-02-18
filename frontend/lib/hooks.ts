/**
 * SWR hooks — typed data fetching hooks for each backend endpoint.
 *
 * SWR cache IS the global state. No Redux/Zustand needed.
 * Each hook has an appropriate refresh interval:
 *   - Dashboard: 30s (balance changes)
 *   - Markets: 60s (predictions update infrequently)
 *   - Queue: 10s (new trades appear)
 *   - Logs: 2s (real-time log viewer)
 *   - Trades/Settings/Performance: 0 (fetch on mount only)
 */

import useSWR, { type SWRConfiguration } from "swr";

import {
  fetchDashboard,
  fetchLogs,
  fetchMarkets,
  fetchPendingTrades,
  fetchPerformance,
  fetchSettings,
  fetchTrades,
} from "./api";
import type {
  BracketPrediction,
  CityCode,
  DashboardData,
  LogEntry,
  PendingTrade,
  PerformanceData,
  TradesPage,
  UserSettings,
} from "./types";

// ─── Dashboard ───

export function useDashboard(config?: SWRConfiguration) {
  return useSWR<DashboardData>(
    "/api/dashboard",
    () => fetchDashboard(),
    {
      refreshInterval: 30_000,
      ...config,
    }
  );
}

// ─── Markets ───

export function useMarkets(city?: CityCode, config?: SWRConfiguration) {
  return useSWR<BracketPrediction[]>(
    city ? `/api/markets?city=${city}` : "/api/markets",
    () => fetchMarkets(city),
    {
      refreshInterval: 60_000,
      ...config,
    }
  );
}

// ─── Pending Trades (Queue) ───

export function usePendingTrades(config?: SWRConfiguration) {
  return useSWR<PendingTrade[]>(
    "/api/queue",
    () => fetchPendingTrades(),
    {
      refreshInterval: 10_000,
      ...config,
    }
  );
}

// ─── Trades (paginated) ───

export function useTrades(
  page: number = 1,
  city?: CityCode,
  status?: string,
  config?: SWRConfiguration
) {
  const params = new URLSearchParams({ page: String(page) });
  if (city) params.set("city", city);
  if (status) params.set("status", status);

  return useSWR<TradesPage>(
    `/api/trades?${params.toString()}`,
    () => fetchTrades(page, city, status),
    {
      refreshInterval: 0,
      ...config,
    }
  );
}

// ─── Settings ───

export function useSettings(config?: SWRConfiguration) {
  return useSWR<UserSettings>(
    "/api/settings",
    () => fetchSettings(),
    {
      refreshInterval: 0,
      ...config,
    }
  );
}

// ─── Logs ───

export function useLogs(
  params?: { module?: string; level?: string; after?: string },
  config?: SWRConfiguration
) {
  const key = params
    ? `/api/logs?${new URLSearchParams(
        Object.entries(params).filter(([, v]) => v) as [string, string][]
      ).toString()}`
    : "/api/logs";

  return useSWR<LogEntry[]>(
    key,
    () => fetchLogs(params),
    {
      refreshInterval: 2_000,
      ...config,
    }
  );
}

// ─── Performance ───

export function usePerformance(config?: SWRConfiguration) {
  return useSWR<PerformanceData>(
    "/api/performance",
    () => fetchPerformance(),
    {
      refreshInterval: 0,
      ...config,
    }
  );
}
