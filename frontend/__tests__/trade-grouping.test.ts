import { describe, expect, it } from "vitest";

import { groupByMarket, groupTrades } from "@/lib/trade-grouping";
import type { TradeRecord } from "@/lib/types";

/** Helper to build a TradeRecord with overrides. */
function makeTrade(overrides: Partial<TradeRecord> = {}): TradeRecord {
  return {
    id: "t1",
    kalshi_order_id: "order-1",
    city: "NYC",
    date: "2026-02-21",
    market_ticker: "KXHIGHNYC-26FEB21-T38",
    bracket_label: "Below 38F",
    side: "yes",
    price_cents: 10,
    quantity: 1,
    model_probability: 0.75,
    market_probability: 0.1,
    ev_at_entry: 0.52,
    confidence: "low",
    status: "OPEN",
    settlement_temp_f: null,
    settlement_source: null,
    pnl_cents: null,
    created_at: "2026-02-21T10:00:00Z",
    settled_at: null,
    ...overrides,
  };
}

describe("groupTrades", () => {
  it("returns empty array for empty input", () => {
    expect(groupTrades([])).toEqual([]);
  });

  it("returns one group for a single trade", () => {
    const trades = [makeTrade()];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(1);
    expect(groups[0].totalQuantity).toBe(1);
    expect(groups[0].trades).toHaveLength(1);
  });

  it("groups trades with same ticker/bracket/side/status", () => {
    const trades = [
      makeTrade({ id: "t1", created_at: "2026-02-21T10:00:00Z" }),
      makeTrade({ id: "t2", created_at: "2026-02-21T10:01:00Z" }),
      makeTrade({ id: "t3", created_at: "2026-02-21T10:02:00Z" }),
    ];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(1);
    expect(groups[0].totalQuantity).toBe(3);
    expect(groups[0].tradeIds).toEqual(["t1", "t2", "t3"]);
  });

  it("keeps trades with different sides separate", () => {
    const trades = [
      makeTrade({ id: "t1", side: "yes" }),
      makeTrade({ id: "t2", side: "no" }),
    ];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(2);
  });

  it("keeps trades with different statuses separate", () => {
    const trades = [
      makeTrade({ id: "t1", status: "OPEN" }),
      makeTrade({ id: "t2", status: "WON", pnl_cents: 90 }),
    ];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(2);
  });

  it("keeps trades with different brackets separate", () => {
    const trades = [
      makeTrade({ id: "t1", bracket_label: "Below 38F" }),
      makeTrade({ id: "t2", bracket_label: "38-40F" }),
    ];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(2);
  });

  it("calculates VWAP correctly", () => {
    const trades = [
      makeTrade({ id: "t1", price_cents: 25, quantity: 2 }),
      makeTrade({ id: "t2", price_cents: 30, quantity: 1 }),
    ];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(1);
    // VWAP = (25*2 + 30*1) / (2+1) = 80/3 ≈ 27
    expect(groups[0].vwapCents).toBe(27);
    expect(groups[0].totalQuantity).toBe(3);
    expect(groups[0].totalCostCents).toBe(80);
  });

  it("sums P&L for settled trades", () => {
    const trades = [
      makeTrade({ id: "t1", status: "WON", pnl_cents: 75 }),
      makeTrade({ id: "t2", status: "WON", pnl_cents: 90 }),
    ];
    const groups = groupTrades(trades);
    expect(groups[0].totalPnlCents).toBe(165);
  });

  it("returns null P&L for OPEN trades", () => {
    const trades = [
      makeTrade({ id: "t1", status: "OPEN" }),
      makeTrade({ id: "t2", status: "OPEN" }),
    ];
    const groups = groupTrades(trades);
    expect(groups[0].totalPnlCents).toBeNull();
  });

  it("picks highest confidence in the group", () => {
    const trades = [
      makeTrade({ id: "t1", confidence: "low" }),
      makeTrade({ id: "t2", confidence: "high" }),
      makeTrade({ id: "t3", confidence: "medium" }),
    ];
    const groups = groupTrades(trades);
    expect(groups[0].confidence).toBe("high");
  });

  it("calculates weighted average model probability", () => {
    const trades = [
      makeTrade({ id: "t1", model_probability: 0.8, quantity: 2 }),
      makeTrade({ id: "t2", model_probability: 0.5, quantity: 1 }),
    ];
    const groups = groupTrades(trades);
    // (0.8*2 + 0.5*1) / 3 = 2.1/3 = 0.7
    expect(groups[0].avgModelProbability).toBeCloseTo(0.7);
  });

  it("tracks earliest and latest created_at", () => {
    const trades = [
      makeTrade({ id: "t1", created_at: "2026-02-21T10:00:00Z" }),
      makeTrade({ id: "t2", created_at: "2026-02-21T12:00:00Z" }),
      makeTrade({ id: "t3", created_at: "2026-02-21T08:00:00Z" }),
    ];
    const groups = groupTrades(trades);
    expect(groups[0].earliestCreatedAt).toBe("2026-02-21T08:00:00Z");
    expect(groups[0].latestCreatedAt).toBe("2026-02-21T12:00:00Z");
  });

  it("picks settlement info from a settled trade", () => {
    const trades = [
      makeTrade({ id: "t1", status: "WON", pnl_cents: 90 }),
      makeTrade({
        id: "t2",
        status: "WON",
        pnl_cents: 90,
        settlement_temp_f: 35.0,
        settlement_source: "NWS",
      }),
    ];
    const groups = groupTrades(trades);
    expect(groups[0].settlement_temp_f).toBe(35.0);
    expect(groups[0].settlement_source).toBe("NWS");
  });

  it("handles null market_ticker with city+date fallback", () => {
    const trades = [
      makeTrade({ id: "t1", market_ticker: null }),
      makeTrade({ id: "t2", market_ticker: null }),
    ];
    const groups = groupTrades(trades);
    expect(groups).toHaveLength(1);
    expect(groups[0].totalQuantity).toBe(2);
  });

  it("sorts groups newest first", () => {
    const trades = [
      makeTrade({
        id: "t1",
        bracket_label: "Old",
        created_at: "2026-02-20T10:00:00Z",
      }),
      makeTrade({
        id: "t2",
        bracket_label: "New",
        created_at: "2026-02-21T10:00:00Z",
      }),
    ];
    const groups = groupTrades(trades);
    expect(groups[0].bracket_label).toBe("New");
    expect(groups[1].bracket_label).toBe("Old");
  });

  it("preserves quantity > 1 on a single trade", () => {
    const trades = [makeTrade({ id: "t1", quantity: 5 })];
    const groups = groupTrades(trades);
    expect(groups[0].totalQuantity).toBe(5);
  });
});

describe("groupByMarket", () => {
  it("returns empty array for empty input", () => {
    expect(groupByMarket([])).toEqual([]);
  });

  it("creates one market group for same city+date", () => {
    const trades = [
      makeTrade({ id: "t1", bracket_label: "Below 38F" }),
      makeTrade({ id: "t2", bracket_label: "38-40F" }),
    ];
    const markets = groupByMarket(trades);
    expect(markets).toHaveLength(1);
    expect(markets[0].groups).toHaveLength(2);
    expect(markets[0].city).toBe("NYC");
  });

  it("creates separate market groups for different cities", () => {
    const trades = [
      makeTrade({ id: "t1", city: "NYC" }),
      makeTrade({
        id: "t2",
        city: "CHI",
        market_ticker: "KXHIGHCHI-26FEB21-T30",
      }),
    ];
    const markets = groupByMarket(trades);
    expect(markets).toHaveLength(2);
  });

  it("creates separate market groups for different dates", () => {
    const trades = [
      makeTrade({ id: "t1", date: "2026-02-21" }),
      makeTrade({
        id: "t2",
        date: "2026-02-22",
        market_ticker: "KXHIGHNYC-26FEB22-T38",
      }),
    ];
    const markets = groupByMarket(trades);
    expect(markets).toHaveLength(2);
  });

  it("sorts markets by date descending", () => {
    const trades = [
      makeTrade({ id: "t1", date: "2026-02-20" }),
      makeTrade({
        id: "t2",
        date: "2026-02-22",
        market_ticker: "KXHIGHNYC-26FEB22-T38",
      }),
    ];
    const markets = groupByMarket(trades);
    expect(markets[0].date).toBe("2026-02-22");
    expect(markets[1].date).toBe("2026-02-20");
  });

  it("generates human-readable market label", () => {
    const trades = [makeTrade()];
    const markets = groupByMarket(trades);
    expect(markets[0].label).toContain("New York");
    expect(markets[0].label).toContain("High Temp");
  });
});
