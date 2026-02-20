"use client";

import {
  ArrowDownWideNarrow,
  ArrowUpWideNarrow,
  ClipboardList,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { mutate } from "swr";

import PendingTradeCard from "@/components/trade-card/pending-trade-card";
import EmptyState from "@/components/ui/empty-state";
import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { approveTrade, rejectTrade } from "@/lib/api";
import { usePendingTrades, useSettings } from "@/lib/hooks";
import type { ConfidenceLevel, PendingTrade } from "@/lib/types";

// ─── Sort Logic ───

type SortField = "ev" | "model" | "confidence" | "city" | "price";
type SortDirection = "asc" | "desc";

const SORT_OPTIONS: { field: SortField; label: string }[] = [
  { field: "ev", label: "EV" },
  { field: "model", label: "Model %" },
  { field: "confidence", label: "Confidence" },
  { field: "city", label: "City" },
  { field: "price", label: "Price" },
];

const CONFIDENCE_ORDER: Record<ConfidenceLevel, number> = {
  high: 3,
  medium: 2,
  low: 1,
};

function sortTrades(
  trades: PendingTrade[],
  field: SortField,
  direction: SortDirection,
): PendingTrade[] {
  const sorted = [...trades].sort((a, b) => {
    let cmp = 0;
    switch (field) {
      case "ev":
        cmp = a.ev - b.ev;
        break;
      case "model":
        cmp = a.model_probability - b.model_probability;
        break;
      case "confidence":
        cmp = CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence];
        break;
      case "city":
        cmp = a.city.localeCompare(b.city);
        break;
      case "price":
        cmp = a.price_cents - b.price_cents;
        break;
    }
    return direction === "desc" ? -cmp : cmp;
  });
  return sorted;
}

// ─── Component ───

export default function QueuePage() {
  const { data: trades, error, isLoading } = usePendingTrades();
  const { data: settings } = useSettings();
  const { showToast } = useToast();
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>("ev");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const sortedTrades = useMemo(() => {
    if (!trades || trades.length === 0) return trades;
    return sortTrades(trades, sortField, sortDirection);
  }, [trades, sortField, sortDirection]);

  const handleSortClick = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDirection((d) => (d === "desc" ? "asc" : "desc"));
      } else {
        setSortField(field);
        setSortDirection("desc");
      }
    },
    [sortField],
  );

  // Optimistically remove a trade card from the list before the API call completes.
  // If the call fails, SWR revalidation restores the card automatically.
  const optimisticRemove = useCallback((id: string) => {
    mutate(
      "/api/queue",
      (current: PendingTrade[] | undefined) =>
        current ? current.filter((t) => t.id !== id) : current,
      false,
    );
  }, []);

  const handleApprove = useCallback(
    async (id: string) => {
      setLoadingId(id);
      optimisticRemove(id);
      try {
        await approveTrade(id);
        showToast({
          variant: "success",
          title: "Trade approved!",
          message: "Your order has been placed on Kalshi.",
        });
        await mutate("/api/queue");
        await mutate("/api/dashboard");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Something went wrong";

        // Detect "not filled" / resting orders
        if (message.toLowerCase().includes("not filled") || message.toLowerCase().includes("resting")) {
          showToast({
            variant: "warning",
            title: "Order not filled",
            message:
              "No one is taking the other side of this trade right now. Try again later or reject it.",
            duration: 6000,
          });
        } else if (message.includes("REJECTED") || message.includes("APPROVED") || message.includes("EXPIRED")) {
          showToast({
            variant: "info",
            title: "Trade already handled",
            message: "This trade was already processed. Refreshing your queue.",
          });
        } else {
          showToast({
            variant: "warning",
            title: "Approve failed",
            message,
            duration: 5000,
          });
        }
        await mutate("/api/queue");
      } finally {
        setLoadingId(null);
      }
    },
    [optimisticRemove, showToast],
  );

  const handleReject = useCallback(
    async (id: string) => {
      setLoadingId(id);
      optimisticRemove(id);
      try {
        await rejectTrade(id);
        showToast({
          variant: "info",
          title: "Trade rejected",
          message: "The trade has been removed from your queue.",
        });
        await mutate("/api/queue");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Something went wrong";

        if (message.includes("REJECTED")) {
          showToast({
            variant: "info",
            title: "Already rejected",
            message: "This trade was already rejected. Refreshing your queue.",
          });
        } else {
          showToast({
            variant: "warning",
            title: "Reject failed",
            message,
            duration: 5000,
          });
        }
        await mutate("/api/queue");
      } finally {
        setLoadingId(null);
      }
    },
    [optimisticRemove, showToast],
  );

  const isAutoMode = settings?.trading_mode === "auto";

  return (
    <ErrorBoundary>
      <h1 className="text-xl font-bold mb-4">Trade Queue</h1>

      {isAutoMode && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-sm text-boz-primary">
          Auto mode is enabled. Trades are executed automatically without
          requiring manual approval.
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-boz-danger">
          {error.message || "Unable to load trade queue"}
        </div>
      )}

      {trades && trades.length === 0 && (
        <EmptyState
          icon={ClipboardList}
          title="No Pending Trades"
          description="When the model identifies +EV opportunities, they'll appear here for your review."
        />
      )}

      {sortedTrades && sortedTrades.length > 0 && (
        <>
          {/* Sort bar */}
          <div className="flex items-center gap-1.5 mb-3 overflow-x-auto pb-1">
            <span className="text-xs text-boz-neutral whitespace-nowrap mr-0.5">
              Sort:
            </span>
            {SORT_OPTIONS.map(({ field, label }) => {
              const isActive = sortField === field;
              const SortIcon =
                sortDirection === "desc"
                  ? ArrowDownWideNarrow
                  : ArrowUpWideNarrow;
              return (
                <button
                  key={field}
                  onClick={() => handleSortClick(field)}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                    isActive
                      ? "bg-boz-primary text-white"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  }`}
                >
                  {label}
                  {isActive && <SortIcon size={12} />}
                </button>
              );
            })}
          </div>

          {/* Trade count */}
          <p className="text-xs text-boz-neutral mb-2">
            {sortedTrades.length} pending trade
            {sortedTrades.length !== 1 ? "s" : ""}
          </p>

          {/* Trade cards */}
          <div className="space-y-3">
            {sortedTrades.map((trade) => (
              <PendingTradeCard
                key={trade.id}
                trade={trade}
                onApprove={handleApprove}
                onReject={handleReject}
                isLoading={loadingId === trade.id}
              />
            ))}
          </div>
        </>
      )}
    </ErrorBoundary>
  );
}
