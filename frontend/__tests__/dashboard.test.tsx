import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DashboardData } from "@/lib/types";

// Mock hooks
const mockUseDashboard = vi.fn();
vi.mock("@/lib/hooks", () => ({
  useDashboard: () => mockUseDashboard(),
}));

// Mock next/navigation for BottomNav
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

import DashboardPage from "@/app/page";

const MOCK_DASHBOARD: DashboardData = {
  balance_cents: 50000,
  today_pnl_cents: 350,
  active_positions: [],
  recent_trades: [
    {
      id: "t1",
      kalshi_order_id: "order-1",
      city: "NYC",
      date: "2025-02-18",
      bracket_label: "55-56°F",
      side: "yes",
      price_cents: 25,
      quantity: 1,
      model_probability: 0.3,
      market_probability: 0.25,
      ev_at_entry: 0.05,
      confidence: "medium",
      status: "WON",
      settlement_temp_f: 55.5,
      settlement_source: "NWS",
      pnl_cents: 75,
      created_at: "2025-02-18T10:00:00Z",
      settled_at: "2025-02-18T18:00:00Z",
    },
  ],
  next_market_launch: "2025-02-19T06:00:00-05:00",
  predictions: [
    {
      city: "NYC",
      date: "2025-02-18",
      brackets: [
        {
          bracket_label: "≤52°F",
          lower_bound_f: null,
          upper_bound_f: 52,
          probability: 0.08,
        },
        {
          bracket_label: "53-54°F",
          lower_bound_f: 53,
          upper_bound_f: 54,
          probability: 0.15,
        },
        {
          bracket_label: "55-56°F",
          lower_bound_f: 55,
          upper_bound_f: 56,
          probability: 0.3,
        },
        {
          bracket_label: "57-58°F",
          lower_bound_f: 57,
          upper_bound_f: 58,
          probability: 0.28,
        },
        {
          bracket_label: "59-60°F",
          lower_bound_f: 59,
          upper_bound_f: 60,
          probability: 0.12,
        },
        {
          bracket_label: "≥61°F",
          lower_bound_f: 61,
          upper_bound_f: null,
          probability: 0.07,
        },
      ],
      ensemble_mean_f: 56.3,
      ensemble_std_f: 2.1,
      confidence: "medium",
      model_sources: ["NWS", "GFS", "ECMWF", "ICON"],
      generated_at: "2025-02-18T06:00:00Z",
    },
  ],
};

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeletons", () => {
    mockUseDashboard.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: true,
    });

    render(<DashboardPage />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    // Check for skeleton elements (aria-hidden divs with animate-pulse)
    const skeletons = document.querySelectorAll('[aria-hidden="true"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state", () => {
    mockUseDashboard.mockReturnValue({
      data: undefined,
      error: new Error("Server down"),
      isLoading: false,
    });

    render(<DashboardPage />);
    expect(screen.getByText("Server down")).toBeInTheDocument();
  });

  it("renders dashboard data", () => {
    mockUseDashboard.mockReturnValue({
      data: MOCK_DASHBOARD,
      error: undefined,
      isLoading: false,
    });

    render(<DashboardPage />);

    // Balance
    expect(screen.getByText("$500.00")).toBeInTheDocument();
    // Today P&L
    expect(screen.getByText("+$3.50")).toBeInTheDocument();
    // Predictions section
    expect(screen.getByText("Today's Predictions")).toBeInTheDocument();
    expect(screen.getByText("New York")).toBeInTheDocument();
  });

  it("renders recent trades", () => {
    mockUseDashboard.mockReturnValue({
      data: MOCK_DASHBOARD,
      error: undefined,
      isLoading: false,
    });

    render(<DashboardPage />);
    expect(screen.getByText("Recent Trades")).toBeInTheDocument();
    expect(screen.getByText("55-56°F")).toBeInTheDocument();
    expect(screen.getByText("WON")).toBeInTheDocument();
  });

  it("handles empty dashboard", () => {
    const emptyDashboard: DashboardData = {
      balance_cents: 10000,
      today_pnl_cents: 0,
      active_positions: [],
      recent_trades: [],
      next_market_launch: null,
      predictions: [],
    };

    mockUseDashboard.mockReturnValue({
      data: emptyDashboard,
      error: undefined,
      isLoading: false,
    });

    render(<DashboardPage />);
    expect(screen.getByText("$100.00")).toBeInTheDocument();
    expect(screen.getByText("+$0.00")).toBeInTheDocument();
  });
});
