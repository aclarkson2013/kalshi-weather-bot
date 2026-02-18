# Agent 5: Frontend (PWA Dashboard)

## Your Mission

Build the Progressive Web App dashboard using Next.js. This is what users see — onboarding, live dashboard, trade queue, trade history with post-mortems, settings, and log viewer. It must work great on iPhone (home screen installable), Android, and desktop.

## What You Build

```
frontend/
├── app/                    → Next.js App Router
│   ├── layout.tsx          → Root layout with navigation
│   ├── page.tsx            → Dashboard (home)
│   ├── onboarding/         → Step-by-step Kalshi API key setup
│   ├── markets/            → Active markets with model vs. market prices
│   ├── trades/             → Trade history + post-mortems
│   ├── queue/              → Pending trade approval queue (manual mode)
│   ├── settings/           → Risk controls, trading mode, city selection
│   ├── logs/               → Log viewer with filters
│   └── performance/        → P&L charts, accuracy metrics
├── components/             → Reusable UI components
│   ├── ui/                 → Base UI primitives (buttons, cards, inputs)
│   ├── charts/             → P&L charts, probability visualizations
│   ├── trade-card/         → Trade display with post-mortem expandable
│   └── bracket-view/       → Visual bracket probability display
├── lib/                    → Utilities, API client, types
│   ├── api.ts              → Backend API client (fetch wrapper)
│   ├── types.ts            → TypeScript types matching backend schemas
│   ├── hooks.ts            → SWR data fetching hooks
│   ├── notifications.ts    → Web Push notification helpers
│   └── utils.ts            → Formatting, date helpers
├── public/
│   ├── manifest.json       → PWA manifest
│   ├── sw.js               → Service worker (via next-pwa / Workbox)
│   └── icons/              → App icons (multiple sizes)
├── __tests__/              → Vitest + React Testing Library test files
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── postcss.config.js
└── package.json
```

## Tech Stack

- **Framework:** Next.js 14+ with App Router
- **Styling:** Tailwind CSS
- **PWA:** next-pwa (wraps Workbox) for service worker, manifest, offline support
- **Charts:** Recharts (lightweight, React-native)
- **Data Fetching:** SWR (stale-while-revalidate) — NOT React Query
- **Icons:** lucide-react (lightweight, tree-shakable)
- **Testing:** Vitest + React Testing Library
- **Linting:** ESLint + Prettier, strict TypeScript

---

## Project Setup & Configuration

### next.config.js

```javascript
// next.config.js
const withPWA = require('next-pwa')({
  dest: 'public',
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === 'development',
});

module.exports = withPWA({
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
});
```

### tailwind.config.ts

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Boz Weather Trader brand colors
        'boz-primary': '#2563eb',    // Blue — primary actions, branding, chart lines
        'boz-success': '#16a34a',    // Green — positive EV, wins, profit
        'boz-danger': '#dc2626',     // Red — negative EV, losses, errors
        'boz-warning': '#d97706',    // Amber — cooldown active, pending states
        'boz-neutral': '#6b7280',    // Gray — disabled, secondary text
      },
    },
  },
  plugins: [],
}
export default config
```

### postcss.config.js

```javascript
// postcss.config.js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

### tsconfig.json Path Aliases

```json
{
  "compilerOptions": {
    "strict": true,
    "paths": {
      "@/*": ["./*"]
    }
  }
}
```

This enables imports like `import { api } from '@/lib/api'` and `import { TradeCard } from '@/components/trade-card/trade-card'`.

### Environment Variables

```bash
# .env.local (never committed — add to .gitignore)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_VAPID_PUBLIC_KEY=<your-vapid-public-key>
```

Only `NEXT_PUBLIC_` prefixed variables are available in client-side code. The VAPID key is public (the private key stays on the backend).

### Package Dependencies

```json
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "swr": "^2.0.0",
    "recharts": "^2.0.0",
    "lucide-react": "^0.300.0",
    "next-pwa": "^5.6.0"
  },
  "devDependencies": {
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0",
    "typescript": "^5.0.0",
    "tailwindcss": "^3.0.0",
    "postcss": "^8.0.0",
    "autoprefixer": "^10.0.0",
    "@testing-library/react": "^14.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "vitest": "^1.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "jsdom": "^23.0.0",
    "eslint": "^8.0.0",
    "eslint-config-next": "^14.0.0",
    "prettier": "^3.0.0"
  }
}
```

---

## TypeScript Types (lib/types.ts)

These MUST match the backend Pydantic schemas in `backend/common/schemas.py` exactly. When the backend schema changes, update these types to match. All monetary values from the API are in **cents** (integers) — the frontend converts to dollars for display only.

```typescript
// lib/types.ts

// ─── Core Enums ─────────────────────────────────────────────
export type City = 'NYC' | 'CHI' | 'MIA' | 'AUS';

// ─── Weather Data (from Agent 1) ────────────────────────────
export interface WeatherVariables {
  temp_high_f: number;
  temp_low_f: number | null;
  humidity_pct: number | null;
  wind_speed_mph: number | null;
  wind_gust_mph: number | null;
  cloud_cover_pct: number | null;
  dew_point_f: number | null;
  pressure_mb: number | null;
}

export interface WeatherData {
  city: City;
  date: string;              // ISO date string "2026-02-17"
  forecast_high_f: number;
  source: string;            // "NWS", "Open-Meteo:GFS", "Open-Meteo:ECMWF"
  model_run_timestamp: string;  // ISO datetime
  variables: WeatherVariables;
  fetched_at: string;        // ISO datetime
}

// ─── Bracket Predictions (from Agent 3) ─────────────────────
export interface BracketProbability {
  bracket_label: string;      // e.g., "53-54°F"
  lower_bound_f: number | null;  // null for bottom edge bracket
  upper_bound_f: number | null;  // null for top edge bracket
  probability: number;         // 0.0 to 1.0 (all 6 brackets sum to 1.0)
}

export interface BracketPrediction {
  city: City;
  date: string;               // ISO date
  brackets: BracketProbability[];  // exactly 6 items
  ensemble_mean_f: number;
  ensemble_std_f: number;
  confidence: 'high' | 'medium' | 'low';
  generated_at: string;       // ISO datetime
  model_sources: string[];    // e.g., ["NWS", "Open-Meteo:GFS", "Open-Meteo:ECMWF"]
}

// ─── Trade Signal (from Agent 4) ────────────────────────────
export interface TradeSignal {
  city: City;
  bracket: string;            // bracket_label
  side: 'yes' | 'no';
  price_cents: number;        // market price in cents
  quantity: number;
  model_probability: number;  // 0.0 to 1.0
  market_probability: number; // 0.0 to 1.0 (derived from market price)
  ev: number;                 // expected value
  confidence: string;
  market_ticker: string;      // Kalshi ticker symbol
}

// ─── Trade Record (stored trades) ───────────────────────────
export interface TradeRecord {
  id: string;
  kalshi_order_id: string;
  city: City;
  bracket: string;
  side: 'yes' | 'no';
  price_cents: number;
  quantity: number;
  model_probability: number;
  market_probability: number;
  ev: number;
  confidence: string;
  status: 'OPEN' | 'WON' | 'LOST' | 'CANCELED';
  pnl_cents: number | null;  // null while OPEN
  placed_at: string;         // ISO datetime
  settled_at: string | null;
  postmortem: PostMortem | null;
}

// ─── Post-Mortem (settled trade analysis) ───────────────────
export interface PostMortem {
  trade_id: string;
  actual_temp_f: number;
  actual_bracket: string;
  forecast_at_trade_time: number;
  model_sources_accuracy: Record<string, number>;  // source name -> accuracy score
  narrative: string;          // LLM-generated explanation of what happened
  pnl_after_fees: number;    // in cents
}

// ─── Pending Trade (manual mode queue) ──────────────────────
export interface PendingTrade {
  id: string;
  city: City;
  bracket: string;
  side: 'yes' | 'no';
  price: number;             // cents
  quantity: number;
  model_probability: number;
  market_probability: number;
  ev: number;
  confidence: string;
  reasoning: string;         // why the bot wants this trade
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'EXECUTED';
  created_at: string;
  expires_at: string;        // trades expire if not acted on
  acted_at: string | null;
}

// ─── User Settings ──────────────────────────────────────────
export interface UserSettings {
  trading_mode: 'auto' | 'manual';
  max_trade_size_cents: number;       // max dollars per trade (in cents)
  daily_loss_limit_cents: number;     // stop trading if daily loss exceeds this
  max_daily_exposure_cents: number;   // max total exposure per day
  min_ev_threshold: number;           // 0.0 to 1.0 — minimum EV to trigger trade
  cooldown_per_loss_minutes: number;  // minutes to wait after a loss
  consecutive_loss_limit: number;     // halt after N consecutive losses
  active_cities: City[];              // which cities to trade
  notifications_enabled: boolean;
}

// ─── Dashboard Aggregate ────────────────────────────────────
export interface DashboardData {
  balance_cents: number;              // Kalshi account balance
  today_pnl_cents: number;           // today's profit/loss
  active_positions: TradeRecord[];    // currently open trades
  recent_trades: TradeRecord[];       // last N settled trades
  next_market_launch: string | null;  // ISO datetime of next market open
  predictions: BracketPrediction[];   // current predictions for all cities
}

// ─── Log Entry ──────────────────────────────────────────────
export interface LogEntry {
  id: number;
  timestamp: string;          // ISO datetime
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL';
  module: string;             // WEATHER, TRADING, ORDER, RISK, etc.
  message: string;
  data: Record<string, unknown> | null;
}

// ─── Performance Metrics ────────────────────────────────────
export interface PerformanceData {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;            // 0.0 to 1.0
  total_pnl_cents: number;
  best_trade_pnl_cents: number;
  worst_trade_pnl_cents: number;
  cumulative_pnl: { date: string; cumulative_pnl: number }[];
  pnl_by_city: Record<City, number>;
  accuracy_over_time: { date: string; accuracy: number }[];
}
```

### Utility: Displaying Cents as Dollars

All monetary values from the API are integers in cents. ALWAYS convert for display:

```typescript
// lib/utils.ts
export function centsToDollars(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function formatPnL(cents: number): string {
  const dollars = cents / 100;
  const sign = dollars >= 0 ? '+' : '';
  return `${sign}$${dollars.toFixed(2)}`;
}

export function formatProbability(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

// City display names
export const CITY_NAMES: Record<City, string> = {
  NYC: 'New York (Central Park)',
  CHI: 'Chicago (Midway)',
  MIA: 'Miami (MIA)',
  AUS: 'Austin (AUS)',
};
```

---

## API Client (lib/api.ts)

All backend communication goes through this single file. The backend runs on FastAPI at the URL specified by `NEXT_PUBLIC_API_URL`. Auth is managed via httpOnly cookies — the frontend never touches API keys directly.

```typescript
// lib/api.ts
import type {
  DashboardData,
  BracketPrediction,
  TradeRecord,
  PendingTrade,
  UserSettings,
  LogEntry,
  PerformanceData,
  City,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── Error Class ────────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ─── Core Fetch Wrapper ─────────────────────────────────────
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    credentials: 'include', // Send httpOnly session cookie
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(
      response.status,
      error.detail || error.message || `HTTP ${response.status}`,
      error.context,
    );
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ─── API Methods ────────────────────────────────────────────
export const api = {
  // ── Auth / Onboarding ──
  validateKeys: (keyId: string, privateKey: string) =>
    fetchApi<{ valid: boolean; balance_cents: number }>('/api/auth/validate', {
      method: 'POST',
      body: JSON.stringify({ key_id: keyId, private_key: privateKey }),
    }),

  disconnect: () =>
    fetchApi<void>('/api/auth/disconnect', { method: 'POST' }),

  // ── Dashboard ──
  getDashboard: () =>
    fetchApi<DashboardData>('/api/dashboard'),

  // ── Markets / Predictions ──
  getMarkets: (city?: City) =>
    fetchApi<BracketPrediction[]>(
      `/api/markets${city ? `?city=${city}` : ''}`,
    ),

  // ── Trades ──
  getTrades: (params?: { city?: City; status?: string; page?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.city) searchParams.set('city', params.city);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page) searchParams.set('page', String(params.page));
    const qs = searchParams.toString();
    return fetchApi<{ trades: TradeRecord[]; total: number; page: number }>(
      `/api/trades${qs ? `?${qs}` : ''}`,
    );
  },

  // ── Trade Queue (manual mode) ──
  getPendingTrades: () =>
    fetchApi<PendingTrade[]>('/api/queue'),

  approveTrade: (tradeId: string) =>
    fetchApi<TradeRecord>(`/api/queue/${tradeId}/approve`, { method: 'POST' }),

  rejectTrade: (tradeId: string) =>
    fetchApi<void>(`/api/queue/${tradeId}/reject`, { method: 'POST' }),

  // ── Settings ──
  getSettings: () =>
    fetchApi<UserSettings>('/api/settings'),

  updateSettings: (settings: Partial<UserSettings>) =>
    fetchApi<UserSettings>('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings),
    }),

  // ── Logs ──
  getLogs: (params?: { module?: string; level?: string; after?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.module) searchParams.set('module', params.module);
    if (params?.level) searchParams.set('level', params.level);
    if (params?.after) searchParams.set('after', params.after);
    const qs = searchParams.toString();
    return fetchApi<LogEntry[]>(`/api/logs${qs ? `?${qs}` : ''}`);
  },

  // ── Performance ──
  getPerformance: () =>
    fetchApi<PerformanceData>('/api/performance'),

  // ── Push Notifications ──
  subscribePush: (subscription: PushSubscription) =>
    fetchApi<void>('/api/notifications/subscribe', {
      method: 'POST',
      body: JSON.stringify(subscription),
    }),
};
```

### Handling Auth Errors Globally

If any API call returns 401 (session expired / not logged in), redirect to onboarding:

```typescript
// In the fetchApi function or in a SWR onError handler:
if (response.status === 401) {
  // Session expired or not authenticated
  if (typeof window !== 'undefined') {
    window.location.href = '/onboarding';
  }
}
```

---

## Data Fetching Pattern (SWR Hooks)

Use SWR for ALL data fetching. SWR provides caching, automatic revalidation, error retry, and optimistic updates out of the box. Do NOT use React Query, raw useEffect+fetch, or any other pattern.

```typescript
// lib/hooks.ts
import useSWR from 'swr';
import { api } from './api';
import type {
  DashboardData,
  PendingTrade,
  UserSettings,
  BracketPrediction,
  TradeRecord,
  LogEntry,
  PerformanceData,
  City,
} from './types';

// ─── Dashboard (refresh every 30s) ─────────────────────────
export function useDashboard() {
  const { data, error, isLoading, mutate } = useSWR<DashboardData>(
    '/api/dashboard',
    () => api.getDashboard(),
    { refreshInterval: 30000 },
  );
  return { dashboard: data, error, isLoading, refresh: mutate };
}

// ─── Trade Queue (refresh every 10s — trades can expire) ───
export function usePendingTrades() {
  const { data, error, isLoading, mutate } = useSWR<PendingTrade[]>(
    '/api/queue',
    () => api.getPendingTrades(),
    { refreshInterval: 10000 },
  );
  return { pendingTrades: data || [], error, isLoading, refresh: mutate };
}

// ─── Markets (refresh every 60s) ────────────────────────────
export function useMarkets(city?: City) {
  const key = city ? `/api/markets?city=${city}` : '/api/markets';
  const { data, error, isLoading, mutate } = useSWR<BracketPrediction[]>(
    key,
    () => api.getMarkets(city),
    { refreshInterval: 60000 },
  );
  return { predictions: data || [], error, isLoading, refresh: mutate };
}

// ─── Trades (paginated, no auto-refresh) ────────────────────
export function useTrades(params?: { city?: City; status?: string; page?: number }) {
  const key = `/api/trades?${JSON.stringify(params || {})}`;
  const { data, error, isLoading, mutate } = useSWR(
    key,
    () => api.getTrades(params),
  );
  return {
    trades: data?.trades || [],
    total: data?.total || 0,
    page: data?.page || 1,
    error,
    isLoading,
    refresh: mutate,
  };
}

// ─── Settings (no auto-refresh, with optimistic update) ─────
export function useSettings() {
  const { data, error, isLoading, mutate } = useSWR<UserSettings>(
    '/api/settings',
    () => api.getSettings(),
  );

  const updateSettings = async (updates: Partial<UserSettings>) => {
    const updated = await api.updateSettings(updates);
    mutate(updated, false); // Optimistic update — don't revalidate
    return updated;
  };

  return { settings: data, error, isLoading, updateSettings };
}

// ─── Logs (refresh every 2s for near-real-time) ─────────────
export function useLogs(params?: { module?: string; level?: string }) {
  const key = `/api/logs?${JSON.stringify(params || {})}`;
  const { data, error, isLoading, mutate } = useSWR<LogEntry[]>(
    key,
    () => api.getLogs(params),
    { refreshInterval: 2000 },
  );
  return { logs: data || [], error, isLoading, refresh: mutate };
}

// ─── Performance (no auto-refresh) ──────────────────────────
export function usePerformance() {
  const { data, error, isLoading } = useSWR<PerformanceData>(
    '/api/performance',
    () => api.getPerformance(),
  );
  return { performance: data, error, isLoading };
}
```

### Refresh Interval Reference

| Hook              | Interval  | Reason                                      |
|-------------------|-----------|---------------------------------------------|
| `useDashboard`    | 30s       | Balance and positions update moderately      |
| `usePendingTrades`| 10s       | Trades can expire — need fast updates        |
| `useMarkets`      | 60s       | Predictions update on model runs             |
| `useTrades`       | none      | Historical data, user-triggered refresh      |
| `useSettings`     | none      | Only changes when user edits                 |
| `useLogs`         | 2s        | Near-real-time log streaming                 |
| `usePerformance`  | none      | Historical aggregate, refresh on demand      |

---

## Root Layout & Navigation

### app/layout.tsx

```tsx
// app/layout.tsx
import { Inter } from 'next/font/google';
import './globals.css';
import { BottomNav } from '@/components/ui/bottom-nav';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'Boz Weather Trader',
  description: 'Automated weather prediction market trading',
  manifest: '/manifest.json',
  themeColor: '#2563eb',
  viewport: 'width=device-width, initial-scale=1, maximum-scale=1',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 pb-16 lg:pb-0 lg:pl-64`}>
        <main className="max-w-lg mx-auto px-4 py-4 lg:max-w-4xl">
          {children}
        </main>
        <BottomNav />
      </body>
    </html>
  );
}
```

### globals.css

```css
/* app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply text-gray-900 antialiased;
  }
}
```

### Bottom Navigation Component

Mobile: fixed bottom tab bar (like native apps). Desktop (lg:): fixed left sidebar.

```tsx
// components/ui/bottom-nav.tsx
'use client';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import {
  LayoutDashboard,
  BarChart3,
  ListChecks,
  History,
  Settings,
} from 'lucide-react';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/markets', label: 'Markets', icon: BarChart3 },
  { href: '/queue', label: 'Queue', icon: ListChecks },
  { href: '/trades', label: 'Trades', icon: History },
  { href: '/settings', label: 'Settings', icon: Settings },
] as const;

export function BottomNav() {
  const pathname = usePathname();

  // Hide nav on onboarding pages
  if (pathname?.startsWith('/onboarding')) return null;

  return (
    <>
      {/* Mobile bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 lg:hidden z-50">
        <div className="flex justify-around items-center h-16 max-w-lg mx-auto">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex flex-col items-center justify-center w-full h-full min-w-[44px] min-h-[44px] ${
                  isActive ? 'text-boz-primary' : 'text-gray-400'
                }`}
              >
                <Icon size={20} />
                <span className="text-xs mt-1">{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Desktop side nav */}
      <nav className="hidden lg:flex fixed left-0 top-0 bottom-0 w-64 bg-white border-r border-gray-200 flex-col p-4 z-50">
        <div className="text-lg font-bold text-boz-primary mb-8 px-3">
          Boz Weather Trader
        </div>
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-3 rounded-lg mb-1 ${
                isActive
                  ? 'bg-blue-50 text-boz-primary font-medium'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              <Icon size={20} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
```

---

## Auth Flow & Session Management

### How Authentication Works

1. **NO passwords** — RSA key-based authentication only (Kalshi API keys).
2. During onboarding, user provides their Kalshi **Key ID** (UUID format) and **PEM private key**.
3. Frontend sends both to backend `POST /api/auth/validate`.
4. Backend validates by making a test Kalshi API call with the provided credentials.
5. If valid: backend encrypts the private key with AES-256, stores it in the database, and sets an **httpOnly session cookie** on the response.
6. The session cookie contains a JWT with user ID (NOT the API keys).
7. **The frontend NEVER stores, caches, or logs the API keys.** Only the session cookie persists.
8. All subsequent API calls include the cookie automatically via `credentials: 'include'`.
9. "Disconnect" flow: `POST /api/auth/disconnect` tells the backend to delete the encrypted keys and clear the session cookie.

### Key Validation Rules (Frontend)

Before sending keys to the backend, validate format client-side:

```typescript
// Key ID: UUID-like format from Kalshi
export function isValidKeyId(keyId: string): boolean {
  return /^[a-f0-9-]{36}$/.test(keyId.trim());
}

// Private key: must be PEM-formatted RSA key
export function isValidPrivateKey(pem: string): boolean {
  const trimmed = pem.trim();
  return /^-----BEGIN (RSA )?PRIVATE KEY-----\n[\s\S]+\n-----END (RSA )?PRIVATE KEY-----$/.test(trimmed);
}
```

---

## Onboarding Flow Implementation

The onboarding flow is a 6-step wizard. Each step must complete before advancing. The user can go back to previous steps.

```tsx
// app/onboarding/page.tsx
'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

const STEPS = ['welcome', 'instructions', 'keys', 'validate', 'disclaimer', 'settings'] as const;
type Step = typeof STEPS[number];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('welcome');
  const [keyId, setKeyId] = useState('');
  const [privateKey, setPrivateKey] = useState('');
  const [balance, setBalance] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(false);

  const stepIndex = STEPS.indexOf(step);

  const goNext = () => {
    if (stepIndex < STEPS.length - 1) setStep(STEPS[stepIndex + 1]);
  };
  const goBack = () => {
    if (stepIndex > 0) setStep(STEPS[stepIndex - 1]);
  };

  const handleValidate = async () => {
    setError(null);
    setIsValidating(true);
    try {
      const result = await api.validateKeys(keyId.trim(), privateKey.trim());
      if (result.valid) {
        setBalance(result.balance_cents);
        goNext(); // Advance to disclaimer step
      } else {
        setError('Keys were not accepted by Kalshi. Please check and try again.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed');
    } finally {
      setIsValidating(false);
    }
  };

  const handleComplete = () => {
    router.push('/'); // Go to dashboard
  };

  // Render current step...
  // Each step is a self-contained component within this page
  // Step 1 (welcome): App name, logo, brief description, "Get Started" button
  // Step 2 (instructions): Visual guide showing how to generate Kalshi API keys
  // Step 3 (keys): Key ID input + Private Key textarea with format validation
  // Step 4 (validate): Loading spinner while backend validates, success/error display
  // Step 5 (disclaimer): Risk acknowledgment checkbox, must accept to continue
  // Step 6 (settings): Trading mode selector, max trade size, city checkboxes
}
```

### Step Details

| Step | Content | Validation |
|------|---------|------------|
| `welcome` | App name, tagline, what the bot does | None — just "Get Started" button |
| `instructions` | Screenshots/diagrams of Kalshi key generation (step-by-step) | None — just "Next" button |
| `keys` | Key ID input (text) + Private Key input (textarea, monospace font) | Key ID matches UUID format, PEM starts with header |
| `validate` | Spinner while calling `/api/auth/validate`, then shows success + balance | Backend must return `valid: true` |
| `disclaimer` | Risk warning text, checkbox "I understand this uses real money" | Checkbox must be checked |
| `settings` | Trading mode (auto/manual), max trade size slider, city checkboxes | At least 1 city selected, valid ranges |

---

## PWA Manifest & Service Worker

### public/manifest.json

```json
{
  "name": "Boz Weather Trader",
  "short_name": "BozWeather",
  "description": "Automated weather prediction market trading",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#2563eb",
  "orientation": "portrait",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

### Service Worker Caching Strategy

next-pwa handles service worker generation via Workbox. The caching strategy should be:

| Resource Type | Strategy | Rationale |
|---------------|----------|-----------|
| App shell (HTML, layout, navigation) | Cache-first | Fast load, update in background |
| API data (`/api/*`) | Network-first with stale-while-revalidate | Always try fresh data, fall back to cache |
| Static assets (JS, CSS bundles) | Cache-first, long TTL | Immutable after build |
| Fonts | Cache-first, long TTL | Rarely change |
| Icons / images | Cache-first | Rarely change |

### Icon Sizes Required

Generate app icons at these sizes and place in `public/icons/`:
- `icon-192.png` (192x192) — standard PWA icon
- `icon-512.png` (512x512) — splash screen
- `icon-maskable-512.png` (512x512, with safe zone padding) — Android adaptive icon
- `favicon.ico` (32x32) — browser tab

---

## Web Push Notification Setup

```typescript
// lib/notifications.ts
import { api } from './api';

export async function subscribeToPushNotifications(): Promise<boolean> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.warn('Push notifications not supported in this browser');
    return false;
  }

  try {
    const registration = await navigator.serviceWorker.ready;

    // Check if already subscribed
    const existingSubscription = await registration.pushManager.getSubscription();
    if (existingSubscription) {
      // Already subscribed — send to backend in case it lost the record
      await api.subscribePush(existingSubscription);
      return true;
    }

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(
        process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY!,
      ),
    });

    // Send subscription to backend for storage
    await api.subscribePush(subscription);
    return true;
  } catch (error) {
    console.error('Failed to subscribe to push notifications:', error);
    return false;
  }
}

export async function unsubscribeFromPushNotifications(): Promise<boolean> {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await subscription.unsubscribe();
    }
    return true;
  } catch (error) {
    console.error('Failed to unsubscribe from push notifications:', error);
    return false;
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}
```

### When to Prompt for Notifications

- During onboarding step 6 (settings), offer a "Enable push notifications" toggle.
- If the user enables it, call `subscribeToPushNotifications()`.
- The backend sends push notifications for: trade executed, trade settled (win/loss), risk limit hit, cooldown started, system errors.

---

## Error Boundary & Loading States

### Error Boundary

```tsx
// components/ui/error-boundary.tsx
'use client';
import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="p-4 bg-red-50 rounded-lg text-center">
            <p className="text-red-800 font-medium">Something went wrong</p>
            <p className="text-red-600 text-sm mt-1">
              {this.state.error?.message}
            </p>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="mt-3 px-4 py-2 bg-red-600 text-white rounded-md text-sm"
            >
              Try Again
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
```

### Loading Skeleton

```tsx
// components/ui/skeleton.tsx
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-gray-200 rounded ${className || ''}`} />
  );
}
```

### Empty State

```tsx
// components/ui/empty-state.tsx
import { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Icon size={48} className="text-gray-300 mb-4" />
      <p className="text-gray-700 font-medium">{title}</p>
      <p className="text-gray-500 text-sm mt-1">{description}</p>
    </div>
  );
}
```

### Standard Pattern for All Pages

Every page that fetches data MUST handle three states: loading, error, and empty. Use this pattern:

```tsx
// Example: any data-driven page
'use client';
import { useDashboard } from '@/lib/hooks';
import { Skeleton } from '@/components/ui/skeleton';

export default function SomePage() {
  const { dashboard, error, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 rounded-lg">
        <p className="text-red-800 font-medium">Failed to load data</p>
        <p className="text-red-600 text-sm">{error.message}</p>
      </div>
    );
  }

  if (!dashboard) return null;

  // Render actual content...
}
```

---

## Responsive Design Breakpoints

Mobile-first design. All base styles target 375px (iPhone SE width).

| Breakpoint | Width  | Target Device | Layout Changes |
|------------|--------|---------------|----------------|
| base       | 0px+   | iPhone SE     | Single column, bottom nav, text-sm |
| `sm:`      | 640px  | Large phones  | Slightly more horizontal space |
| `md:`      | 768px  | Tablets       | 2-column grids where appropriate |
| `lg:`      | 1024px | Desktop       | Side nav replaces bottom nav, wider cards |

### Key Rules

- **Bottom nav on mobile, side nav on desktop (lg:)** — see layout.tsx above.
- **Cards stack vertically on mobile, grid on desktop** — use `grid grid-cols-1 lg:grid-cols-2 gap-4`.
- **Font sizes:** base `text-sm` on mobile, `lg:text-base` on desktop.
- **Touch targets:** minimum 44x44px on ALL interactive elements (buttons, links, toggles). Use `min-h-[44px] min-w-[44px]` on tap targets.
- **Test at 375px width** for ALL components. Use Chrome DevTools responsive mode.
- **Max content width:** `max-w-lg` (512px) on mobile, `lg:max-w-4xl` on desktop.

---

## Key Component Patterns

### Trade Card

Displays a single trade with win/loss styling and expandable post-mortem.

```tsx
// components/trade-card/trade-card.tsx
'use client';
import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { TradeRecord } from '@/lib/types';
import { centsToDollars, formatPnL, formatDate, formatProbability } from '@/lib/utils';

interface TradeCardProps {
  trade: TradeRecord;
  expandable?: boolean;
}

export function TradeCard({ trade, expandable = true }: TradeCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isWin = trade.status === 'WON';
  const isOpen = trade.status === 'OPEN';

  const borderColor = isOpen
    ? 'border-gray-200'
    : isWin
      ? 'border-green-200'
      : 'border-red-200';
  const bgColor = isOpen
    ? 'bg-white'
    : isWin
      ? 'bg-green-50'
      : 'bg-red-50';

  return (
    <div className={`p-4 rounded-lg border ${borderColor} ${bgColor}`}>
      {/* Header row */}
      <div className="flex justify-between items-center">
        <div>
          <span className="font-medium text-sm">{trade.city}</span>
          <span className="text-gray-500 text-sm ml-2">{trade.bracket}</span>
          <span className="text-gray-400 text-xs ml-2 uppercase">{trade.side}</span>
        </div>
        <div className="text-right">
          {trade.pnl_cents !== null ? (
            <span className={`font-bold text-sm ${isWin ? 'text-boz-success' : 'text-boz-danger'}`}>
              {formatPnL(trade.pnl_cents)}
            </span>
          ) : (
            <span className="text-gray-500 text-sm">Open</span>
          )}
        </div>
      </div>

      {/* Details row */}
      <div className="flex justify-between mt-2 text-xs text-gray-500">
        <span>Model: {formatProbability(trade.model_probability)}</span>
        <span>Market: {formatProbability(trade.market_probability)}</span>
        <span>EV: {trade.ev.toFixed(3)}</span>
      </div>

      {/* Timestamp */}
      <div className="text-xs text-gray-400 mt-1">
        {formatDate(trade.placed_at)}
      </div>

      {/* Expandable post-mortem */}
      {expandable && trade.postmortem && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-sm text-boz-primary mt-3 min-h-[44px]"
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            {expanded ? 'Hide' : 'Show'} Post-Mortem
          </button>
          {expanded && (
            <div className="mt-2 p-3 bg-white rounded border border-gray-100 text-sm">
              <p className="text-gray-700">{trade.postmortem.narrative}</p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-500">
                <div>Actual: {trade.postmortem.actual_temp_f}F</div>
                <div>Bracket: {trade.postmortem.actual_bracket}</div>
                <div>Forecast: {trade.postmortem.forecast_at_trade_time}F</div>
                <div>Net P&L: {formatPnL(trade.postmortem.pnl_after_fees)}</div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

### Pending Trade Card (Queue)

```tsx
// components/trade-card/pending-trade-card.tsx
'use client';
import { useState } from 'react';
import type { PendingTrade } from '@/lib/types';
import { api } from '@/lib/api';
import { formatProbability, centsToDollars } from '@/lib/utils';

interface PendingTradeCardProps {
  trade: PendingTrade;
  onAction: () => void; // called after approve/reject to refresh list
}

export function PendingTradeCard({ trade, onAction }: PendingTradeCardProps) {
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    setLoading(true);
    try {
      await api.approveTrade(trade.id);
      onAction();
    } catch (err) {
      console.error('Failed to approve trade:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await api.rejectTrade(trade.id);
      onAction();
    } catch (err) {
      console.error('Failed to reject trade:', err);
    } finally {
      setLoading(false);
    }
  };

  // Calculate time remaining until expiration
  const expiresAt = new Date(trade.expires_at);
  const now = new Date();
  const minutesLeft = Math.max(0, Math.round((expiresAt.getTime() - now.getTime()) / 60000));

  return (
    <div className="p-4 rounded-lg border border-blue-200 bg-blue-50">
      <div className="flex justify-between items-start">
        <div>
          <span className="font-medium">{trade.city}</span>
          <span className="text-gray-500 ml-2">{trade.bracket}</span>
          <span className="ml-2 text-xs uppercase font-medium text-boz-primary">{trade.side}</span>
        </div>
        <span className="text-xs text-boz-warning">{minutesLeft}m left</span>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-3 text-xs text-gray-600">
        <div>Price: {centsToDollars(trade.price)}c</div>
        <div>Model: {formatProbability(trade.model_probability)}</div>
        <div className="text-boz-success font-medium">EV: +{trade.ev.toFixed(3)}</div>
      </div>

      <p className="text-xs text-gray-500 mt-2 italic">{trade.reasoning}</p>

      <div className="flex gap-3 mt-4">
        <button
          onClick={handleApprove}
          disabled={loading}
          className="flex-1 bg-boz-success text-white py-2 rounded-lg text-sm font-medium min-h-[44px] disabled:opacity-50"
        >
          Approve
        </button>
        <button
          onClick={handleReject}
          disabled={loading}
          className="flex-1 bg-gray-200 text-gray-700 py-2 rounded-lg text-sm font-medium min-h-[44px] disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
```

### Bracket View (Model vs Market)

Visual comparison of model probability vs market price for each bracket. Shows 6 horizontal bars for a city's prediction.

```tsx
// components/bracket-view/bracket-view.tsx
import type { BracketPrediction } from '@/lib/types';
import { formatProbability } from '@/lib/utils';

interface BracketViewProps {
  prediction: BracketPrediction;
  marketPrices: Record<string, number>; // bracket_label -> price in cents (0-100)
}

export function BracketView({ prediction, marketPrices }: BracketViewProps) {
  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-medium">{prediction.city}</h3>
        <span className="text-xs text-gray-500">
          Confidence: {prediction.confidence}
        </span>
      </div>

      {prediction.brackets.map((bracket) => {
        const marketPrice = marketPrices[bracket.bracket_label] ?? 0;
        const marketProb = marketPrice / 100; // cents -> probability
        const modelProb = bracket.probability;
        const evPositive = modelProb > marketProb;
        const barMaxWidth = 100; // percentage

        return (
          <div key={bracket.bracket_label} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="font-medium w-20">{bracket.bracket_label}</span>
              <span className={evPositive ? 'text-boz-success font-medium' : 'text-boz-danger'}>
                {evPositive ? '+EV' : '-EV'}
              </span>
            </div>

            {/* Model probability bar (blue) */}
            <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 bg-boz-primary rounded-full"
                style={{ width: `${modelProb * barMaxWidth}%` }}
              />
            </div>

            {/* Market probability bar (gray) */}
            <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 bg-gray-400 rounded-full"
                style={{ width: `${marketProb * barMaxWidth}%` }}
              />
            </div>

            <div className="flex justify-between text-xs text-gray-400">
              <span>Model: {formatProbability(modelProb)}</span>
              <span>Market: {formatProbability(marketProb)}</span>
            </div>
          </div>
        );
      })}

      <div className="text-xs text-gray-400 mt-2">
        Sources: {prediction.model_sources.join(', ')}
      </div>
    </div>
  );
}
```

---

## Charts Setup (Recharts)

### Cumulative P&L Chart

```tsx
// components/charts/pnl-chart.tsx
'use client';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

interface PnLChartProps {
  data: { date: string; cumulative_pnl: number }[];
}

export function PnLChart({ data }: PnLChartProps) {
  if (data.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-gray-400 text-sm">
        No trade data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12 }}
          tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        />
        <YAxis
          tick={{ fontSize: 12 }}
          tickFormatter={(v) => `$${(v / 100).toFixed(0)}`}
          width={50}
        />
        <Tooltip
          formatter={(v: number) => [`$${(v / 100).toFixed(2)}`, 'P&L']}
          labelFormatter={(v) => new Date(v).toLocaleDateString()}
        />
        <ReferenceLine y={0} stroke="#d1d5db" strokeDasharray="3 3" />
        <Line
          type="monotone"
          dataKey="cumulative_pnl"
          stroke="#2563eb"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

### Win Rate by City Bar Chart

```tsx
// components/charts/city-performance-chart.tsx
'use client';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { City } from '@/lib/types';

interface CityPerformanceChartProps {
  data: Record<City, number>; // city -> P&L in cents
}

export function CityPerformanceChart({ data }: CityPerformanceChartProps) {
  const chartData = Object.entries(data).map(([city, pnl]) => ({
    city,
    pnl,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chartData}>
        <XAxis dataKey="city" tick={{ fontSize: 12 }} />
        <YAxis tickFormatter={(v) => `$${(v / 100).toFixed(0)}`} tick={{ fontSize: 12 }} width={50} />
        <Tooltip formatter={(v: number) => [`$${(v / 100).toFixed(2)}`, 'P&L']} />
        <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={index} fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
```

---

## Key Pages

### 1. Onboarding (`/onboarding`)
See "Onboarding Flow Implementation" section above. Six steps:
1. Welcome screen
2. API key generation instructions (with visual guide)
3. API key input form (Key ID + Private Key textarea)
4. Validation (call backend to verify keys)
5. Risk disclaimer acknowledgment
6. Initial settings (trading mode, max trade size, cities)

### 2. Dashboard (`/`) — Home
- Account balance (from Kalshi) — display as dollars: `$${centsToDollars(balance_cents)}`
- Today's P&L (color-coded green/red)
- Active positions with current market prices
- Next market launch countdown
- Quick model predictions for upcoming markets
- Recent trade results
- Use `useDashboard()` hook, refresh every 30s

### 3. Markets (`/markets`)
- Market type selector (High Temp active, others "Coming Soon")
- City filter tabs (NYC | CHI | MIA | AUS | All)
- For each city: show 6 brackets with `BracketView` component:
  - Market price (what Kalshi says)
  - Model probability (what we think)
  - EV indicator (green if +EV, red if -EV)
  - Visual bar chart comparing model vs. market
- Use `useMarkets()` hook, refresh every 60s

### 4. Trade Queue (`/queue`) — Manual mode only
- List of pending trades awaiting approval using `PendingTradeCard` components
- Each trade shows: city, bracket, price, model prob, EV, confidence, reasoning
- Approve / Reject buttons (44px min touch target)
- Expiration countdown timer on each card
- Empty state: "No pending trades -- bot is monitoring markets" with `ListChecks` icon
- If user is in auto mode, show message: "Trading is in auto mode. Switch to manual in Settings to review trades."
- Use `usePendingTrades()` hook, refresh every 10s

### 5. Trade History (`/trades`)
- Filterable list of all trades (by city, result, date, confidence)
- Filter controls: city dropdown, status dropdown (All/Won/Lost/Open)
- Each trade rendered with `TradeCard` component, expandable post-mortem
- Summary stats at top: total trades, win rate, total P&L
- Pagination (10 trades per page)
- Use `useTrades()` hook

### 6. Settings (`/settings`)
- Trading mode toggle (Full Auto / Manual Approval) — use a segmented control
- Risk controls:
  - Max trade size: slider with label showing dollar value (range: $0.10 to $10.00)
  - Daily loss limit: slider (range: $1.00 to $50.00)
  - Max exposure: slider (range: $5.00 to $100.00)
  - Min EV threshold: slider (range: 0.01 to 0.20)
- Cooldown settings:
  - Per-loss cooldown: slider showing minutes (range: 15 to 240)
  - Consecutive loss limit: number input (range: 1 to 10)
- City selection: checkboxes for NYC, CHI, MIA, AUS (at least one must be checked)
- Notifications toggle
- API key management section:
  - "Test Connection" button (calls `/api/auth/validate` with existing session)
  - "Disconnect" button (calls `/api/auth/disconnect`, redirects to onboarding)
- Use `useSettings()` hook with optimistic updates

### 7. Log Viewer (`/logs`)
- Near-real-time log streaming (poll backend every 2 seconds via `useLogs()`)
- Filter by module tag dropdown: WEATHER, TRADING, ORDER, RISK, COOLDOWN, AUTH, SETTLE, POSTMORTEM, SYSTEM, MODEL, MARKET
- Filter by log level dropdown: DEBUG, INFO, WARN, ERROR, CRITICAL
- Color-coded log levels: INFO=gray, WARN=amber, ERROR=red, CRITICAL=red bold
- Auto-scroll to bottom (newest logs), with "pin to bottom" toggle
- Monospace font for log messages (`font-mono text-xs`)
- Export button (download as JSON)

### 8. Performance (`/performance`)
- Cumulative P&L chart (line chart over time) — `PnLChart` component
- P&L by city (bar chart) — `CityPerformanceChart` component
- Summary cards: total trades, win rate, total P&L, best trade, worst trade
- Model accuracy over time (line chart showing calibration)
- Use `usePerformance()` hook

---

## PWA Requirements

- `manifest.json` with app name "Boz Weather Trader", theme color `#2563eb`, icons
- Service worker for offline caching (at minimum: app shell, cached dashboard data)
- Web Push notifications (subscribe during onboarding, user can toggle in settings)
- "Add to Home Screen" prompt on mobile (browser handles this if manifest is valid)
- Responsive design: mobile-first, works well at 375px width and up
- Standalone display mode (no browser chrome when launched from home screen)

---

## Testing Requirements

### Test Setup (vitest.config.ts)

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './__tests__/setup.ts',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
});
```

```typescript
// __tests__/setup.ts
import '@testing-library/jest-dom';
```

### Test Files

Your tests go in `frontend/__tests__/`:
- `onboarding.test.tsx` — step transitions, form validation, API key format validation
- `dashboard.test.tsx` — renders with mock data, handles loading/error states
- `trade-queue.test.tsx` — approve/reject flow, expiration display, empty state
- `trade-card.test.tsx` — post-mortem expansion, win/loss styling
- `settings.test.tsx` — form validation, range limits on inputs
- `api.test.ts` — API client error handling, auth token inclusion
- `hooks.test.ts` — SWR hooks return correct data, handle errors
- `utils.test.ts` — centsToDollars, formatPnL, formatProbability, date formatting

### Critical Test Cases

- **Onboarding:** invalid API key format shows error, does not submit to backend
- **Onboarding:** valid key format enables "Validate" button
- **Dashboard:** API returns error shows friendly error message, not crash
- **Dashboard:** loading state shows skeletons, not blank page
- **Trade queue:** trade expires while user is viewing updates UI in real-time
- **Trade queue:** approve button calls `api.approveTrade()` with correct ID
- **Trade queue:** empty state shows when no pending trades exist
- **Trade card:** WON trades have green styling, LOST trades have red styling
- **Trade card:** post-mortem section expands/collapses on click
- **Settings:** slider values stay within valid ranges (cannot exceed min/max)
- **Settings:** at least one city must remain checked
- **Mobile:** key components render correctly at 375px width
- **API client:** 401 response triggers redirect to onboarding
- **API client:** network error shows user-friendly message
- **Cents display:** all dollar amounts correctly divide by 100

### Mocking API Calls in Tests

```typescript
// Example test pattern
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import DashboardPage from '@/app/page';

const mockDashboard: DashboardData = {
  balance_cents: 10050,
  today_pnl_cents: 250,
  active_positions: [],
  recent_trades: [],
  next_market_launch: null,
  predictions: [],
};

// Wrap component in SWRConfig to control fetching in tests
function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {ui}
    </SWRConfig>
  );
}

// Mock the api module
vi.mock('@/lib/api', () => ({
  api: {
    getDashboard: vi.fn().mockResolvedValue(mockDashboard),
  },
}));
```

---

## Build Checklist (Implementation Order)

Follow this order. Each step depends on the previous ones.

1. Initialize Next.js project with TypeScript, Tailwind, PWA (`npx create-next-app@latest --typescript --tailwind --app`)
2. Install dependencies: `swr`, `recharts`, `lucide-react`, `next-pwa`
3. Configure `next.config.js` (PWA), `tailwind.config.ts` (brand colors), `tsconfig.json` (path aliases)
4. Create `lib/types.ts` — all TypeScript types matching backend schemas
5. Create `lib/utils.ts` — formatting helpers (centsToDollars, formatPnL, etc.)
6. Create `lib/api.ts` — API client with fetch wrapper and all endpoints
7. Create `lib/hooks.ts` — SWR data fetching hooks for all endpoints
8. Create `lib/notifications.ts` — Web Push subscription helpers
9. Build base UI components: `components/ui/bottom-nav.tsx`, `error-boundary.tsx`, `skeleton.tsx`, `empty-state.tsx`
10. Build root layout (`app/layout.tsx`) with bottom nav and responsive container
11. Build onboarding flow (`app/onboarding/page.tsx`) — 6-step wizard
12. Build dashboard page (`app/page.tsx`) — home with balance, P&L, positions
13. Build markets page (`app/markets/page.tsx`) — bracket visualization with `BracketView`
14. Build trade queue page (`app/queue/page.tsx`) — approve/reject with `PendingTradeCard`
15. Build trade history page (`app/trades/page.tsx`) — with `TradeCard` and filters
16. Build settings page (`app/settings/page.tsx`) — form with sliders and toggles
17. Build log viewer page (`app/logs/page.tsx`) — real-time log display
18. Build performance page (`app/performance/page.tsx`) — charts with `PnLChart`
19. Build chart components: `components/charts/pnl-chart.tsx`, `city-performance-chart.tsx`
20. Set up PWA manifest (`public/manifest.json`) and generate icons
21. Implement push notifications (subscribe flow during onboarding + settings toggle)
22. Write tests for all pages and components (see testing section)
23. Run `npm test` — all tests must pass
24. Test at 375px width on ALL pages using Chrome DevTools responsive mode
25. Test PWA install flow on Android and iOS Safari

---

## Important Conventions

### Monetary Values
- ALL monetary values from the backend API are in **cents** (integers).
- Display in **dollars** with 2 decimal places: `$${(cents / 100).toFixed(2)}`.
- Use `centsToDollars()` and `formatPnL()` helpers from `lib/utils.ts` everywhere.
- NEVER display raw cent values to the user.

### Component Files
- One component per file.
- File name matches component name in kebab-case: `TradeCard` -> `trade-card.tsx`.
- Co-locate component-specific styles, types, and tests.

### State Management
- Use SWR for server state (all API data).
- Use React `useState` for local UI state (form inputs, toggles, expanded sections).
- NO global state library (no Redux, no Zustand). SWR cache IS the global state.
- If you need to share state between sibling components, lift it to the parent or use SWR's shared cache.

### Error Messages
- Never show raw HTTP errors or stack traces to users.
- Always provide human-readable error messages.
- For network errors: "Unable to connect to server. Please check your connection."
- For 401 errors: redirect to onboarding silently.
- For 400/422 errors: show the `detail` field from the API response.
- For 500 errors: "Something went wrong on our end. Please try again."

### Accessibility
- All images must have `alt` text.
- All form inputs must have associated `<label>` elements.
- Interactive elements must be keyboard-navigable.
- Color is not the only indicator of state (use icons/text alongside color).
- Focus states must be visible.

### Security
- NEVER store, log, or display API keys in the frontend.
- NEVER include API keys in URL parameters.
- All API calls use `credentials: 'include'` for httpOnly cookie auth.
- The session cookie is httpOnly and secure — JavaScript cannot read it.
- Validate all user inputs client-side before sending to backend.
- Sanitize any user-generated content before rendering.
