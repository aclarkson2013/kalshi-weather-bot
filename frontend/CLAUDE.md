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
│   └── utils.ts            → Formatting, date helpers
├── public/
│   ├── manifest.json       → PWA manifest
│   ├── sw.js               → Service worker (via Workbox)
│   └── icons/              → App icons (multiple sizes)
├── __tests__/              → Jest/Vitest test files
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

## Tech Stack

- **Framework:** Next.js 14+ with App Router
- **Styling:** Tailwind CSS
- **PWA:** next-pwa or Workbox for service worker, manifest, offline support
- **Charts:** Recharts or Chart.js (lightweight)
- **State:** React Context or Zustand (keep it simple — no Redux)
- **Testing:** Jest or Vitest + React Testing Library
- **Linting:** ESLint + Prettier, strict TypeScript

## Key Pages

### 1. Onboarding (`/onboarding`)
See PRD Section 3.5. Six steps:
1. Welcome screen
2. API key generation instructions (with visual guide)
3. API key input form (Key ID + Private Key textarea)
4. Validation (call backend to verify keys)
5. Risk disclaimer acknowledgment
6. Initial settings (trading mode, max trade size, cities)

### 2. Dashboard (`/`) — Home
- Account balance (from Kalshi)
- Today's P&L (wins/losses)
- Active positions with current market prices
- Next market launch countdown
- Quick model predictions for upcoming markets
- Recent trade results

### 3. Markets (`/markets`)
- Market type selector (High Temp active, others "Coming Soon")
- For each city: show 6 brackets with:
  - Market price (what Kalshi says)
  - Model probability (what we think)
  - EV indicator (green if +EV, red if -EV)
  - Visual bar chart comparing model vs. market

### 4. Trade Queue (`/queue`) — Manual mode only
- List of pending trades awaiting approval
- Each trade shows: city, bracket, price, model prob, EV, confidence, reasoning
- Approve / Reject buttons
- Expiration countdown timer
- Empty state: "No pending trades — bot is monitoring markets"

### 5. Trade History (`/trades`)
- Filterable list of all trades (by city, result, date, confidence)
- Each trade expandable to show full post-mortem (see PRD Section 3.6)
- Summary stats at top: total trades, win rate, total P&L

### 6. Settings (`/settings`)
- Trading mode toggle (Full Auto / Manual Approval)
- Risk controls: max trade size, daily loss limit, max exposure, min EV threshold
- Cooldown settings: per-loss cooldown (slider), consecutive loss limit (number input)
- City selection: checkboxes for which cities to trade
- API key management: re-enter keys, test connection, disconnect
- Notification preferences

### 7. Log Viewer (`/logs`)
- Real-time log streaming (poll backend every 2 seconds or use WebSocket)
- Filter by module tag (WEATHER, TRADING, ORDER, RISK, etc.)
- Filter by log level (INFO, WARN, ERROR, CRITICAL)
- Date/time range picker
- Search bar for message text
- Export button (CSV/JSON)

### 8. Performance (`/performance`)
- Cumulative P&L chart (line chart over time)
- Win rate by city (bar chart)
- Model accuracy over time (calibration chart)
- Best/worst trades
- ROI metrics

## PWA Requirements

- `manifest.json` with app name "Boz Weather Trader", theme color, icons
- Service worker for offline caching (at minimum: app shell, cached dashboard data)
- Web Push notifications (subscribe during onboarding, user can toggle)
- "Add to Home Screen" prompt on mobile
- Responsive design: mobile-first, works well at 375px width and up

## API Client

All backend communication through `lib/api.ts`:
- Base URL from environment variable
- Auth token in httpOnly cookie (set during onboarding)
- Typed responses matching backend Pydantic models
- Error handling with user-friendly error messages
- Loading states for all async operations

## Testing Requirements

Your tests go in `frontend/__tests__/`:
- `onboarding.test.tsx` — step transitions, form validation, API key format validation
- `dashboard.test.tsx` — renders with mock data, handles loading/error states
- `trade-queue.test.tsx` — approve/reject flow, expiration display, empty state
- `trade-card.test.tsx` — post-mortem expansion, win/loss styling
- `settings.test.tsx` — form validation, range limits on inputs
- `api.test.ts` — API client error handling, auth token inclusion

**Critical test cases:**
- Onboarding: invalid API key format → shows error, doesn't submit
- Dashboard: API returns error → shows friendly error message, not crash
- Trade queue: trade expires while user is viewing → updates UI in real-time
- Settings: slider values stay within valid ranges
- Mobile: key components render correctly at 375px width
