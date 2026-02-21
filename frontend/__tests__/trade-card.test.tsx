import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import TradeCard from "@/components/trade-card/trade-card";
import type { GroupedTrade, TradeRecord } from "@/lib/types";

/** Helper to build a TradeRecord with overrides. */
function makeTrade(overrides: Partial<TradeRecord> = {}): TradeRecord {
  return {
    id: "t1",
    kalshi_order_id: "order-1",
    city: "NYC",
    date: "2025-02-18",
    market_ticker: "KXHIGHNYC-25FEB18-T55",
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
    ...overrides,
  };
}

/** Helper to build a single-trade GroupedTrade. */
function makeGroup(overrides: Partial<GroupedTrade> = {}): GroupedTrade {
  const trade = makeTrade(overrides as Partial<TradeRecord>);
  return {
    groupKey: "KXHIGHNYC-25FEB18-T55|55-56°F|yes|OPEN",
    city: trade.city,
    date: trade.date,
    market_ticker: trade.market_ticker,
    bracket_label: trade.bracket_label,
    side: trade.side,
    status: trade.status,
    confidence: trade.confidence,
    totalQuantity: trade.quantity,
    totalCostCents: trade.price_cents * trade.quantity,
    vwapCents: trade.price_cents,
    totalPnlCents: trade.pnl_cents,
    avgModelProbability: trade.model_probability,
    avgMarketProbability: trade.market_probability,
    avgEvAtEntry: trade.ev_at_entry,
    tradeIds: [trade.id],
    trades: [trade],
    earliestCreatedAt: trade.created_at,
    latestCreatedAt: trade.created_at,
    settlement_temp_f: trade.settlement_temp_f,
    settlement_source: trade.settlement_source,
    ...overrides,
  };
}

describe("TradeCard", () => {
  it("renders trade info", () => {
    render(<TradeCard group={makeGroup()} />);
    expect(screen.getByText("NYC")).toBeInTheDocument();
    expect(screen.getByText("55-56°F")).toBeInTheDocument();
    expect(screen.getByText("OPEN")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
  });

  it("shows green status for WON trades", () => {
    render(
      <TradeCard
        group={makeGroup({
          status: "WON",
          totalPnlCents: 75,
        })}
      />,
    );
    const statusEl = screen.getByText("WON");
    expect(statusEl.className).toContain("boz-success");
  });

  it("shows red status for LOST trades", () => {
    render(
      <TradeCard
        group={makeGroup({
          status: "LOST",
          totalPnlCents: -25,
        })}
      />,
    );
    const statusEl = screen.getByText("LOST");
    expect(statusEl.className).toContain("boz-danger");
  });

  it("shows P&L for settled trades", () => {
    render(
      <TradeCard
        group={makeGroup({
          status: "WON",
          totalPnlCents: 75,
        })}
      />,
    );
    expect(screen.getByText("+$0.75")).toBeInTheDocument();
  });

  it("shows negative P&L for lost trades", () => {
    render(
      <TradeCard
        group={makeGroup({
          status: "LOST",
          totalPnlCents: -25,
        })}
      />,
    );
    expect(screen.getByText("-$0.25")).toBeInTheDocument();
  });

  it("does not show P&L for open trades", () => {
    render(<TradeCard group={makeGroup()} />);
    expect(screen.queryByText(/\$0\./)).not.toBeInTheDocument();
  });

  it("expands to show details on click", () => {
    render(<TradeCard group={makeGroup()} />);

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
    render(
      <TradeCard
        group={makeGroup({
          status: "WON",
          totalPnlCents: 75,
          settlement_temp_f: 55.5,
          settlement_source: "NWS",
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("55.5°F")).toBeInTheDocument();
    expect(screen.getByText("NWS")).toBeInTheDocument();
  });

  it("collapses details on second click", () => {
    render(<TradeCard group={makeGroup()} />);

    // Expand
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Model Prob:")).toBeInTheDocument();

    // Collapse
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("Model Prob:")).not.toBeInTheDocument();
  });

  // --- New tests for grouped trades ---

  it("shows quantity badge for multi-trade groups", () => {
    render(<TradeCard group={makeGroup({ totalQuantity: 3 })} />);
    expect(screen.getByText("x3")).toBeInTheDocument();
  });

  it("does not show quantity badge for single trades", () => {
    render(<TradeCard group={makeGroup({ totalQuantity: 1 })} />);
    expect(screen.queryByText("x1")).not.toBeInTheDocument();
  });

  it("shows VWAP with avg suffix for multi-trade groups", () => {
    render(
      <TradeCard
        group={makeGroup({
          totalQuantity: 3,
          vwapCents: 27,
          trades: [
            makeTrade({ id: "t1", price_cents: 25 }),
            makeTrade({ id: "t2", price_cents: 30 }),
            makeTrade({ id: "t3", price_cents: 25 }),
          ],
        })}
      />,
    );
    // Text is split across JSX nodes, so use a function matcher
    expect(
      screen.getByText((_, el) => {
        return el?.tagName === "SPAN" && el?.textContent?.includes("0.27") && el?.textContent?.includes("avg") || false;
      }),
    ).toBeInTheDocument();
  });

  it("does not show avg suffix for single-trade groups", () => {
    render(<TradeCard group={makeGroup()} />);
    expect(screen.queryByText(/avg/)).not.toBeInTheDocument();
  });

  it("shows individual orders sub-list when expanded for multi-trade group", () => {
    render(
      <TradeCard
        group={makeGroup({
          totalQuantity: 2,
          trades: [
            makeTrade({ id: "t1", price_cents: 25, created_at: "2025-02-18T10:00:00Z" }),
            makeTrade({ id: "t2", price_cents: 30, created_at: "2025-02-18T10:05:00Z" }),
          ],
        })}
      />,
    );

    // Expand
    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("Individual Orders (2)")).toBeInTheDocument();
    expect(screen.getByText(/1x @ \$0\.25/)).toBeInTheDocument();
    expect(screen.getByText(/1x @ \$0\.30/)).toBeInTheDocument();
  });

  it("does not show individual orders for single-trade group", () => {
    render(<TradeCard group={makeGroup()} />);

    // Expand
    fireEvent.click(screen.getByRole("button"));

    expect(screen.queryByText(/Individual Orders/)).not.toBeInTheDocument();
  });
});
