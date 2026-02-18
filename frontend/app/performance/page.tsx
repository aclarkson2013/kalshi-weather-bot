"use client";

import { BarChart3 } from "lucide-react";

import CityPerformanceChart from "@/components/charts/city-performance-chart";
import PnlChart from "@/components/charts/pnl-chart";
import EmptyState from "@/components/ui/empty-state";
import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import { usePerformance } from "@/lib/hooks";
import { centsToDollars, formatPnL, formatProbability } from "@/lib/utils";

export default function PerformancePage() {
  const { data, error, isLoading } = usePerformance();

  if (isLoading) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4">Performance</h1>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4">Performance</h1>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-boz-danger">
          {error.message || "Unable to load performance data"}
        </div>
      </div>
    );
  }

  if (!data || data.total_trades === 0) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4">Performance</h1>
        <EmptyState
          icon={BarChart3}
          title="No Performance Data"
          description="Performance metrics will appear after your first settled trades."
        />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <h1 className="text-xl font-bold mb-4">Performance</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <span className="text-xs text-boz-neutral">Total Trades</span>
          <div className="text-lg font-bold">{data.total_trades}</div>
          <span className="text-xs text-boz-neutral">
            {data.wins}W / {data.losses}L
          </span>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <span className="text-xs text-boz-neutral">Win Rate</span>
          <div className="text-lg font-bold text-boz-primary">
            {formatProbability(data.win_rate)}
          </div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <span className="text-xs text-boz-neutral">Total P&L</span>
          <div
            className={`text-lg font-bold ${
              data.total_pnl_cents >= 0
                ? "text-boz-success"
                : "text-boz-danger"
            }`}
          >
            {formatPnL(data.total_pnl_cents)}
          </div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <span className="text-xs text-boz-neutral">Best / Worst</span>
          <div className="text-sm">
            <span className="text-boz-success font-medium">
              {formatPnL(data.best_trade_pnl_cents)}
            </span>
            {" / "}
            <span className="text-boz-danger font-medium">
              {formatPnL(data.worst_trade_pnl_cents)}
            </span>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="space-y-4">
        <PnlChart data={data.cumulative_pnl} />
        <CityPerformanceChart pnlByCity={data.pnl_by_city} />

        {/* Accuracy Over Time */}
        {data.accuracy_over_time.length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <h3 className="text-sm font-semibold mb-3">
              Daily Win Rate Over Time
            </h3>
            <div className="space-y-1">
              {data.accuracy_over_time.map((point) => (
                <div
                  key={point.date}
                  className="flex items-center gap-2 text-xs"
                >
                  <span className="text-boz-neutral w-20">{point.date}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                    <div
                      className="h-full bg-boz-primary rounded-full"
                      style={{ width: `${point.accuracy * 100}%` }}
                    />
                  </div>
                  <span className="font-medium w-10 text-right">
                    {formatProbability(point.accuracy)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
