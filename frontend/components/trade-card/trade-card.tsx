"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import type { GroupedTrade } from "@/lib/types";
import {
  centsToDollars,
  confidenceBadgeColor,
  formatDate,
  formatDateTime,
  formatPnL,
  formatProbability,
  settlementCountdown,
  statusColor,
  tradeFinancials,
} from "@/lib/utils";

interface TradeCardProps {
  group: GroupedTrade;
}

/**
 * Trade card displaying a GroupedTrade — one or more orders on the same
 * bracket/side/status, aggregated into a single card with total quantity.
 * Green for WON, red for LOST, blue for OPEN, gray for CANCELED.
 */
export default function TradeCard({ group }: TradeCardProps) {
  const [expanded, setExpanded] = useState(false);

  const isSettled = group.status === "WON" || group.status === "LOST";
  const isMulti = group.trades.length > 1;
  const countdown = settlementCountdown(group.market_ticker, isSettled);
  const { costCents, profitCents } = tradeFinancials(
    group.vwapCents,
    group.totalQuantity,
    group.side,
  );
  const borderColor =
    group.status === "WON"
      ? "border-l-boz-success"
      : group.status === "LOST"
        ? "border-l-boz-danger"
        : group.status === "OPEN"
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
            <span className="font-semibold text-sm">{group.city}</span>
            <span className="text-xs text-boz-neutral">
              {group.bracket_label}
            </span>
            {group.totalQuantity > 1 && (
              <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-700">
                x{group.totalQuantity}
              </span>
            )}
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full ${confidenceBadgeColor(group.confidence)}`}
            >
              {group.confidence}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-boz-neutral">
              {formatDate(group.date)}
            </span>
            <span className="text-xs text-boz-neutral">
              {group.side.toUpperCase()} @ {centsToDollars(group.vwapCents)}
              {isMulti ? " avg" : ""}
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
            <span className={`text-sm font-semibold ${statusColor(group.status)}`}>
              {group.status}
            </span>
            {isSettled && group.totalPnlCents !== null && (
              <div
                className={`text-sm font-medium ${
                  group.totalPnlCents >= 0 ? "text-boz-success" : "text-boz-danger"
                }`}
              >
                {formatPnL(group.totalPnlCents)}
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
              {formatProbability(group.avgModelProbability)}
            </div>
            <div>
              <span className="text-boz-neutral">Market Prob:</span>{" "}
              {formatProbability(group.avgMarketProbability)}
            </div>
            <div>
              <span className="text-boz-neutral">EV at Entry:</span>{" "}
              {(group.avgEvAtEntry * 100).toFixed(1)}%
            </div>
            <div>
              <span className="text-boz-neutral">Quantity:</span>{" "}
              {group.totalQuantity}
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
            {group.settlement_temp_f !== null && (
              <div>
                <span className="text-boz-neutral">Settlement:</span>{" "}
                {group.settlement_temp_f}°F
              </div>
            )}
            {group.settlement_source && (
              <div>
                <span className="text-boz-neutral">Source:</span>{" "}
                {group.settlement_source}
              </div>
            )}
          </div>

          {/* Individual orders list for multi-trade groups */}
          {isMulti && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <h4 className="text-xs font-semibold text-boz-neutral mb-2">
                Individual Orders ({group.trades.length})
              </h4>
              <div className="space-y-1">
                {group.trades.map((trade) => (
                  <div
                    key={trade.id}
                    className="flex justify-between text-xs text-gray-600"
                  >
                    <span>
                      {trade.quantity}x @ ${centsToDollars(trade.price_cents)}
                    </span>
                    <span className="text-boz-neutral">
                      {formatDateTime(trade.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
