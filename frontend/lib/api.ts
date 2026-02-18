/**
 * API client — typed fetch wrapper for all 13 backend endpoints.
 *
 * All functions throw on non-OK responses. 401 errors redirect to /onboarding.
 */

import type {
  AuthValidateRequest,
  AuthValidateResponse,
  BracketPrediction,
  CityCode,
  DashboardData,
  LogEntry,
  PendingTrade,
  PerformanceData,
  PushSubscriptionPayload,
  SettingsUpdate,
  TradeRecord,
  TradesPage,
  UserSettings,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Fetch Wrapper ───

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${path}`;

  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  // 401 → redirect to onboarding
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      window.location.href = "/onboarding";
    }
    throw new ApiError("Not authenticated", 401);
  }

  // 204 No Content → return undefined
  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let message = `Request failed: ${res.status}`;
    try {
      const body = await res.json();
      message = body.detail || body.message || message;
    } catch {
      // Use default message
    }
    throw new ApiError(message, res.status);
  }

  return res.json();
}

// ─── Auth (2 endpoints) ───

export async function validateCredentials(
  creds: AuthValidateRequest
): Promise<AuthValidateResponse> {
  return apiFetch<AuthValidateResponse>("/api/auth/validate", {
    method: "POST",
    body: JSON.stringify(creds),
  });
}

export async function disconnect(): Promise<void> {
  return apiFetch<void>("/api/auth/disconnect", {
    method: "POST",
  });
}

// ─── Dashboard (1 endpoint) ───

export async function fetchDashboard(): Promise<DashboardData> {
  return apiFetch<DashboardData>("/api/dashboard");
}

// ─── Markets (1 endpoint) ───

export async function fetchMarkets(
  city?: CityCode
): Promise<BracketPrediction[]> {
  const params = city ? `?city=${city}` : "";
  return apiFetch<BracketPrediction[]>(`/api/markets${params}`);
}

// ─── Trades (1 endpoint) ───

export async function fetchTrades(
  page: number = 1,
  city?: CityCode,
  status?: string
): Promise<TradesPage> {
  const params = new URLSearchParams({ page: String(page) });
  if (city) params.set("city", city);
  if (status) params.set("status", status);
  return apiFetch<TradesPage>(`/api/trades?${params.toString()}`);
}

// ─── Queue (3 endpoints) ───

export async function fetchPendingTrades(): Promise<PendingTrade[]> {
  return apiFetch<PendingTrade[]>("/api/queue");
}

export async function approveTrade(
  tradeId: string
): Promise<TradeRecord> {
  return apiFetch<TradeRecord>(`/api/queue/${tradeId}/approve`, {
    method: "POST",
  });
}

export async function rejectTrade(tradeId: string): Promise<void> {
  return apiFetch<void>(`/api/queue/${tradeId}/reject`, {
    method: "POST",
  });
}

// ─── Settings (2 endpoints) ───

export async function fetchSettings(): Promise<UserSettings> {
  return apiFetch<UserSettings>("/api/settings");
}

export async function updateSettings(
  update: SettingsUpdate
): Promise<UserSettings> {
  return apiFetch<UserSettings>("/api/settings", {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}

// ─── Logs (1 endpoint) ───

export async function fetchLogs(params?: {
  module?: string;
  level?: string;
  after?: string;
}): Promise<LogEntry[]> {
  const searchParams = new URLSearchParams();
  if (params?.module) searchParams.set("module", params.module);
  if (params?.level) searchParams.set("level", params.level);
  if (params?.after) searchParams.set("after", params.after);
  const qs = searchParams.toString();
  return apiFetch<LogEntry[]>(`/api/logs${qs ? `?${qs}` : ""}`);
}

// ─── Performance (1 endpoint) ───

export async function fetchPerformance(): Promise<PerformanceData> {
  return apiFetch<PerformanceData>("/api/performance");
}

// ─── Notifications (1 endpoint) ───

export async function subscribePush(
  subscription: PushSubscriptionPayload
): Promise<void> {
  return apiFetch<void>("/api/notifications/subscribe", {
    method: "POST",
    body: JSON.stringify(subscription),
  });
}
