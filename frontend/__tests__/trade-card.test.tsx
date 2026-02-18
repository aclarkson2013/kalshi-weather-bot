import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import TradeCard from "@/components/trade-card/trade-card";
import type { TradeRecord } from "@/lib/types";

const BASE_TRADE: TradeRecord = {
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
  status: "OPEN",
  settlement_temp_f: null,
  settlement_source: null,
  pnl_cents: null,
  created_at: "2025-02-18T10:00:00Z",
  settled_at: null,
};

describe("TradeCard", () => {
  it("renders trade info", () => {
    render(<TradeCard trade={BASE_TRADE} />);
    expect(screen.getByText("NYC")).toBeInTheDocument();
    expect(screen.getByText("55-56°F")).toBeInTheDocument();
    expect(screen.getByText("OPEN")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
  });

  it("shows green status for WON trades", () => {
    const wonTrade: TradeRecord = {
      ...BASE_TRADE,
      status: "WON",
      pnl_cents: 75,
      settled_at: "2025-02-18T18:00:00Z",
    };

    render(<TradeCard trade={wonTrade} />);
    const statusEl = screen.getByText("WON");
    expect(statusEl.className).toContain("boz-success");
  });

  it("shows red status for LOST trades", () => {
    const lostTrade: TradeRecord = {
      ...BASE_TRADE,
      status: "LOST",
      pnl_cents: -25,
      settled_at: "2025-02-18T18:00:00Z",
    };

    render(<TradeCard trade={lostTrade} />);
    const statusEl = screen.getByText("LOST");
    expect(statusEl.className).toContain("boz-danger");
  });

  it("shows P&L for settled trades", () => {
    const wonTrade: TradeRecord = {
      ...BASE_TRADE,
      status: "WON",
      pnl_cents: 75,
    };

    render(<TradeCard trade={wonTrade} />);
    expect(screen.getByText("+$0.75")).toBeInTheDocument();
  });

  it("shows negative P&L for lost trades", () => {
    const lostTrade: TradeRecord = {
      ...BASE_TRADE,
      status: "LOST",
      pnl_cents: -25,
    };

    render(<TradeCard trade={lostTrade} />);
    expect(screen.getByText("-$0.25")).toBeInTheDocument();
  });

  it("does not show P&L for open trades", () => {
    render(<TradeCard trade={BASE_TRADE} />);
    expect(screen.queryByText(/\$0\./)).not.toBeInTheDocument();
  });

  it("expands to show details on click", () => {
    render(<TradeCard trade={BASE_TRADE} />);

    // Details should not be visible initially
    expect(screen.queryByText("Model Prob:")).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(screen.getByRole("button"));

    // Details should now be visible
    expect(screen.getByText("Model Prob:")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.getByText("Market Prob:")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("EV at Entry:")).toBeInTheDocument();
  });

  it("shows settlement info for settled trades when expanded", () => {
    const settledTrade: TradeRecord = {
      ...BASE_TRADE,
      status: "WON",
      pnl_cents: 75,
      settlement_temp_f: 55.5,
      settlement_source: "NWS",
    };

    render(<TradeCard trade={settledTrade} />);
    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("55.5°F")).toBeInTheDocument();
    expect(screen.getByText("NWS")).toBeInTheDocument();
  });

  it("collapses details on second click", () => {
    render(<TradeCard trade={BASE_TRADE} />);

    // Expand
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Model Prob:")).toBeInTheDocument();

    // Collapse
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("Model Prob:")).not.toBeInTheDocument();
  });
});
