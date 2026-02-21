import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PendingTrade } from "@/lib/types";

// Mock hooks
const mockUsePendingTrades = vi.fn();
const mockUseSettings = vi.fn();
vi.mock("@/lib/hooks", () => ({
  usePendingTrades: () => mockUsePendingTrades(),
  useSettings: () => mockUseSettings(),
}));

// Mock API
const mockApproveTrade = vi.fn();
const mockRejectTrade = vi.fn();
vi.mock("@/lib/api", () => ({
  approveTrade: (...args: unknown[]) => mockApproveTrade(...args),
  rejectTrade: (...args: unknown[]) => mockRejectTrade(...args),
}));

// Mock toast
const mockShowToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/queue",
}));

import QueuePage from "@/app/queue/page";

const MOCK_TRADE: PendingTrade = {
  id: "pt1",
  city: "NYC",
  bracket: "55-56°F",
  side: "yes",
  price_cents: 22,
  quantity: 1,
  model_probability: 0.3,
  market_probability: 0.22,
  ev: 0.05,
  confidence: "medium",
  reasoning: "Model sees 30% vs market 22%",
  status: "PENDING",
  created_at: "2025-02-18T10:00:00Z",
  expires_at: new Date(Date.now() + 2 * 3600000).toISOString(),
  acted_at: null,
};

describe("QueuePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSettings.mockReturnValue({ data: { trading_mode: "manual" } });
  });

  it("shows empty state with no pending trades", () => {
    mockUsePendingTrades.mockReturnValue({
      data: [],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    expect(screen.getByText("No Pending Trades")).toBeInTheDocument();
  });

  it("renders pending trade cards", () => {
    mockUsePendingTrades.mockReturnValue({
      data: [MOCK_TRADE],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    expect(screen.getByText("NYC")).toBeInTheDocument();
    expect(screen.getByText("55-56°F")).toBeInTheDocument();
    expect(screen.getByText("Model sees 30% vs market 22%")).toBeInTheDocument();
    expect(screen.getByText("Approve")).toBeInTheDocument();
    expect(screen.getByText("Reject")).toBeInTheDocument();
  });

  it("calls approveTrade when approve is clicked", async () => {
    mockApproveTrade.mockResolvedValue({});
    mockUsePendingTrades.mockReturnValue({
      data: [MOCK_TRADE],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    fireEvent.click(screen.getByText("Approve"));

    await waitFor(() => {
      expect(mockApproveTrade).toHaveBeenCalledWith("pt1");
    });
  });

  it("calls rejectTrade when reject is clicked", async () => {
    mockRejectTrade.mockResolvedValue(undefined);
    mockUsePendingTrades.mockReturnValue({
      data: [MOCK_TRADE],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    fireEvent.click(screen.getByText("Reject"));

    await waitFor(() => {
      expect(mockRejectTrade).toHaveBeenCalledWith("pt1");
    });
  });

  it("shows auto mode message", () => {
    mockUseSettings.mockReturnValue({ data: { trading_mode: "auto" } });
    mockUsePendingTrades.mockReturnValue({
      data: [],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    expect(
      screen.getByText(/Auto mode is enabled/i)
    ).toBeInTheDocument();
  });

  it("shows error state", () => {
    mockUsePendingTrades.mockReturnValue({
      data: undefined,
      error: new Error("Connection failed"),
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    expect(screen.getByText("Connection failed")).toBeInTheDocument();
  });

  it("shows loading skeletons", () => {
    mockUsePendingTrades.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: true,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    const skeletons = document.querySelectorAll('[aria-hidden="true"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows EV percentage with correct sign", () => {
    mockUsePendingTrades.mockReturnValue({
      data: [MOCK_TRADE],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    render(<QueuePage />);
    expect(screen.getByText("+5.0%")).toBeInTheDocument();
  });
});
