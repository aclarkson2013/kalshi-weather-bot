"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import type { TradeRecord } from "@/lib/types";
import {
  centsToDollars,
  confidenceBadgeColor,
  formatDate,
  formatPnL,
  formatProbability,
  settlementCountdown,
  statusColor,
  tradeFinancials,
} from "@/lib/utils";

interface TradeCardProps {
  trade: TradeRecord;
}

/**
 * Settled/open trade card with color-coded status and expandable details.
 * Green for WON, red for LOST, blue for OPEN, gray for CANCELED.
 */
export default function TradeCard({ trade }: TradeCardProps) {
  const [expanded, setExpanded] = useState(false);

  const isSettled = trade.status === "WON" || trade.status === "LOST";
  const countdown = settlementCountdown(trade.market_ticker, isSettled);
  const { costCents, profitCents } = tradeFinancials(
    trade.price_cents,
    trade.quantity,
    trade.side,
  );
  const borderColor =
    trade.status === "WON"
      ? "border-l-boz-success"
      : trade.status === "LOST"
        ? "border-l-boz-danger"
        : trade.status === "OPEN"
          ? "border-l-boz-primary"
          : "border-l-boz-neutral";

  return (
    <div
      className={`bg-white rounded-lg border border-gray-200 border-l-4 ${borderColor} shadow-sm`}
    >
      {/* Main row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full min-h-[44px] flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm">{trade.city}</span>
            <span className="text-xs text-boz-neutral">
              {trade.bracket_label}
            </span>
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full ${confidenceBadgeColor(trade.confidence)}`}
            >
              {trade.confidence}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-boz-neutral">
              {formatDate(trade.date)}
            </span>
            <span className="text-xs text-boz-neutral">
              {trade.side.toUpperCase()} @ {centsToDollars(trade.price_cents)}
            </span>
            {countdown && (
              <span className="text-xs font-medium text-boz-warning">
                {countdown}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 ml-2">
          <div className="text-right">
            <span className={`text-sm font-semibold ${statusColor(trade.status)}`}>
              {trade.status}
            </span>
            {isSettled && trade.pnl_cents !== null && (
              <div
                className={`text-sm font-medium ${
                  trade.pnl_cents >= 0 ? "text-boz-success" : "text-boz-danger"
                }`}
              >
                {formatPnL(trade.pnl_cents)}
              </div>
            )}
          </div>
          {expanded ? (
            <ChevronUp size={16} className="text-boz-neutral" />
          ) : (
            <ChevronDown size={16} className="text-boz-neutral" />
          )}
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-3 border-t border-gray-100">
          <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
            <div>
              <span className="text-boz-neutral">Model Prob:</span>{" "}
              {formatProbability(trade.model_probability)}
            </div>
            <div>
              <span className="text-boz-neutral">Market Prob:</span>{" "}
              {formatProbability(trade.market_probability)}
            </div>
            <div>
              <span className="text-boz-neutral">EV at Entry:</span>{" "}
              {(trade.ev_at_entry * 100).toFixed(1)}%
            </div>
            <div>
              <span className="text-boz-neutral">Quantity:</span>{" "}
              {trade.quantity}
            </div>
            <div>
              <span className="text-boz-neutral">Cost:</span>{" "}
              ${(costCents / 100).toFixed(2)}
            </div>
            {!isSettled && (
              <div>
                <span className="text-boz-neutral">Profit if right:</span>{" "}
                <span className="text-boz-success font-medium">
                  +${(profitCents / 100).toFixed(2)}
                </span>
              </div>
            )}
            {trade.settlement_temp_f !== null && (
              <div>
                <span className="text-boz-neutral">Settlement:</span>{" "}
                {trade.settlement_temp_f}°F
              </div>
            )}
            {trade.settlement_source && (
              <div>
                <span className="text-boz-neutral">Source:</span>{" "}
                {trade.settlement_source}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
