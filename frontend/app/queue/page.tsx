"use client";

import { ClipboardList } from "lucide-react";
import { useCallback, useState } from "react";
import { mutate } from "swr";

import PendingTradeCard from "@/components/trade-card/pending-trade-card";
import EmptyState from "@/components/ui/empty-state";
import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import { approveTrade, rejectTrade } from "@/lib/api";
import { usePendingTrades, useSettings } from "@/lib/hooks";

export default function QueuePage() {
  const { data: trades, error, isLoading } = usePendingTrades();
  const { data: settings } = useSettings();
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleApprove = useCallback(async (id: string) => {
    setLoadingId(id);
    setActionError(null);
    try {
      await approveTrade(id);
      // Revalidate queue and dashboard
      await mutate("/api/queue");
      await mutate("/api/dashboard");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setLoadingId(null);
    }
  }, []);

  const handleReject = useCallback(async (id: string) => {
    setLoadingId(id);
    setActionError(null);
    try {
      await rejectTrade(id);
      await mutate("/api/queue");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setLoadingId(null);
    }
  }, []);

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

      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-boz-danger">
          {actionError}
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

      {trades && trades.length > 0 && (
        <div className="space-y-3">
          {trades.map((trade) => (
            <PendingTradeCard
              key={trade.id}
              trade={trade}
              onApprove={handleApprove}
              onReject={handleReject}
              isLoading={loadingId === trade.id}
            />
          ))}
        </div>
      )}
    </ErrorBoundary>
  );
}
