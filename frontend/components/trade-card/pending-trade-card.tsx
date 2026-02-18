"use client";

import { Check, X } from "lucide-react";

import type { PendingTrade } from "@/lib/types";
import {
  centsToDollars,
  confidenceBadgeColor,
  formatProbability,
  timeRemaining,
} from "@/lib/utils";

interface PendingTradeCardProps {
  trade: PendingTrade;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  isLoading?: boolean;
}

/**
 * Pending trade card with EV display, reasoning, and approve/reject buttons.
 * Shows expiration countdown. Touch targets ≥ 44px.
 */
export default function PendingTradeCard({
  trade,
  onApprove,
  onReject,
  isLoading = false,
}: PendingTradeCardProps) {
  const remaining = timeRemaining(trade.expires_at);
  const isExpired = remaining === "Expired";
  const evPercent = (trade.ev * 100).toFixed(1);
  const isPositiveEv = trade.ev > 0;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm">{trade.city}</span>
          <span className="text-xs text-boz-neutral">{trade.bracket}</span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded-full ${confidenceBadgeColor(trade.confidence)}`}
          >
            {trade.confidence}
          </span>
        </div>
        <span
          className={`text-xs font-medium ${
            isExpired ? "text-boz-danger" : "text-boz-neutral"
          }`}
        >
          {remaining}
        </span>
      </div>

      {/* Trade details */}
      <div className="grid grid-cols-2 gap-2 text-xs mb-3">
        <div>
          <span className="text-boz-neutral">Side:</span>{" "}
          {trade.side.toUpperCase()} @ ${centsToDollars(trade.price_cents)}
        </div>
        <div>
          <span className="text-boz-neutral">EV:</span>{" "}
          <span
            className={
              isPositiveEv ? "text-boz-success font-medium" : "text-boz-danger"
            }
          >
            {isPositiveEv ? "+" : ""}
            {evPercent}%
          </span>
        </div>
        <div>
          <span className="text-boz-neutral">Model:</span>{" "}
          {formatProbability(trade.model_probability)}
        </div>
        <div>
          <span className="text-boz-neutral">Market:</span>{" "}
          {formatProbability(trade.market_probability)}
        </div>
      </div>

      {/* Reasoning */}
      {trade.reasoning && (
        <p className="text-xs text-boz-neutral bg-gray-50 rounded p-2 mb-3">
          {trade.reasoning}
        </p>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={() => onApprove(trade.id)}
          disabled={isLoading || isExpired}
          className="flex-1 min-h-[44px] flex items-center justify-center gap-1 bg-boz-success text-white rounded-lg font-medium text-sm hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Check size={16} />
          Approve
        </button>
        <button
          onClick={() => onReject(trade.id)}
          disabled={isLoading || isExpired}
          className="flex-1 min-h-[44px] flex items-center justify-center gap-1 bg-boz-danger text-white rounded-lg font-medium text-sm hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <X size={16} />
          Reject
        </button>
      </div>
    </div>
  );
}
