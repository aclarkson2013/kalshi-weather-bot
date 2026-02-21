"use client";

import { BarChart3, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";

import TradeCard from "@/components/trade-card/trade-card";
import EmptyState from "@/components/ui/empty-state";
import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { syncTrades } from "@/lib/api";
import { useTrades } from "@/lib/hooks";
import type { CityCode, SyncResult, TradeStatus } from "@/lib/types";
import { centsToDollars, formatPnL } from "@/lib/utils";

const CITY_OPTIONS: (CityCode | "ALL")[] = ["ALL", "NYC", "CHI", "MIA", "AUS"];
const STATUS_OPTIONS: (TradeStatus | "ALL")[] = [
  "ALL",
  "OPEN",
  "WON",
  "LOST",
  "CANCELED",
];

export default function TradesPage() {
  const [page, setPage] = useState(1);
  const [cityFilter, setCityFilter] = useState<CityCode | "ALL">("ALL");
  const [statusFilter, setStatusFilter] = useState<TradeStatus | "ALL">("ALL");
  const [syncing, setSyncing] = useState(false);

  const city = cityFilter === "ALL" ? undefined : cityFilter;
  const status = statusFilter === "ALL" ? undefined : statusFilter;
  const { data, error, isLoading, mutate: mutateTrades } = useTrades(page, city, status);
  const { showToast } = useToast();

  const totalPages = data ? Math.ceil(data.total / 20) : 0;

  // Calculate summary stats from current page (visible trades)
  const trades = data?.trades ?? [];
  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl_cents ?? 0), 0);
  const wonCount = trades.filter((t) => t.status === "WON").length;
  const lostCount = trades.filter((t) => t.status === "LOST").length;

  const handleSync = useCallback(async () => {
    setSyncing(true);
    try {
      const result: SyncResult = await syncTrades();
      if (result.synced_count > 0) {
        showToast({
          variant: "success",
          title: "Portfolio synced",
          message: `Synced ${result.synced_count} trade${result.synced_count > 1 ? "s" : ""} from Kalshi`,
        });
        await mutateTrades();
      } else {
        showToast({
          variant: "info",
          title: "Already in sync",
          message: "No new trades found on Kalshi",
        });
      }
    } catch (err) {
      showToast({
        variant: "warning",
        title: "Sync failed",
        message: err instanceof Error ? err.message : "Unable to sync with Kalshi",
      });
    } finally {
      setSyncing(false);
    }
  }, [mutateTrades, showToast]);

  return (
    <ErrorBoundary>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Trade History</h1>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="min-h-[36px] px-3 py-1.5 rounded-lg text-xs font-medium bg-boz-primary text-white hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1.5 transition-colors"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Syncing..." : "Sync from Kalshi"}
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="flex gap-1">
          {CITY_OPTIONS.map((c) => (
            <button
              key={c}
              onClick={() => {
                setCityFilter(c);
                setPage(1);
              }}
              className={`min-h-[36px] px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                cityFilter === c
                  ? "bg-boz-primary text-white"
                  : "bg-white border border-gray-200 text-boz-neutral hover:bg-gray-50"
              }`}
            >
              {c === "ALL" ? "All" : c}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => {
                setStatusFilter(s);
                setPage(1);
              }}
              className={`min-h-[36px] px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === s
                  ? "bg-boz-primary text-white"
                  : "bg-white border border-gray-200 text-boz-neutral hover:bg-gray-50"
              }`}
            >
              {s === "ALL" ? "All" : s}
            </button>
          ))}
        </div>
      </div>

      {/* Summary stats */}
      {data && data.total > 0 && (
        <div className="flex gap-4 mb-4 text-xs">
          <span className="text-boz-neutral">
            {data.total} total trades
          </span>
          {wonCount > 0 && (
            <span className="text-boz-success font-medium">
              {wonCount} won
            </span>
          )}
          {lostCount > 0 && (
            <span className="text-boz-danger font-medium">
              {lostCount} lost
            </span>
          )}
          <span
            className={`font-medium ${
              totalPnl >= 0 ? "text-boz-success" : "text-boz-danger"
            }`}
          >
            Page P&L: {formatPnL(totalPnl)}
          </span>
        </div>
      )}

      {/* Content */}
      {isLoading && (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-boz-danger">
          {error.message || "Unable to load trades"}
        </div>
      )}

      {data && data.trades.length === 0 && (
        <EmptyState
          icon={BarChart3}
          title="No Trades Found"
          description="Your trade history will appear here once you start trading."
        />
      )}

      {data && data.trades.length > 0 && (
        <>
          <div className="space-y-2 mb-4">
            {data.trades.map((trade) => (
              <TradeCard key={trade.id} trade={trade} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-sm text-boz-neutral px-2">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </ErrorBoundary>
  );
}
