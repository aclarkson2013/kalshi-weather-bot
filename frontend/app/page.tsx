"use client";

import {
  Activity,
  Clock,
  DollarSign,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import TradeCard from "@/components/trade-card/trade-card";
import { useDashboard } from "@/lib/hooks";
import type { DashboardData } from "@/lib/types";
import { centsToDollars, formatDateTime, formatPnL, CITY_NAMES } from "@/lib/utils";

function StatCard({
  label,
  value,
  icon: Icon,
  color = "text-gray-900",
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={16} className="text-boz-neutral" />
        <span className="text-xs text-boz-neutral">{label}</span>
      </div>
      <span className={`text-lg font-bold ${color}`}>{value}</span>
    </div>
  );
}

function DashboardContent({ data }: { data: DashboardData }) {
  const pnlColor =
    data.today_pnl_cents >= 0 ? "text-boz-success" : "text-boz-danger";
  const PnlIcon = data.today_pnl_cents >= 0 ? TrendingUp : TrendingDown;

  return (
    <>
      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <StatCard
          label="Balance"
          value={`$${centsToDollars(data.balance_cents)}`}
          icon={DollarSign}
        />
        <StatCard
          label="Today P&L"
          value={formatPnL(data.today_pnl_cents)}
          icon={PnlIcon}
          color={pnlColor}
        />
        <StatCard
          label="Open Positions"
          value={String(data.active_positions.length)}
          icon={Activity}
        />
        <StatCard
          label="Next Launch"
          value={data.next_market_launch ? formatDateTime(data.next_market_launch) : "—"}
          icon={Clock}
        />
      </div>

      {/* Predictions Summary */}
      {data.predictions.length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">
            Today&apos;s Predictions
          </h2>
          <div className="space-y-2">
            {data.predictions.map((pred) => (
              <div
                key={pred.city}
                className="bg-white rounded-lg border border-gray-200 shadow-sm p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">
                    {CITY_NAMES[pred.city]}
                  </span>
                  <span className="text-xs text-boz-neutral">
                    {pred.ensemble_mean_f.toFixed(0)}°F ±
                    {pred.ensemble_std_f.toFixed(1)}
                  </span>
                </div>
                <div className="flex gap-1 mt-2">
                  {pred.brackets.map((b) => (
                    <div
                      key={b.bracket_label}
                      className="flex-1 text-center"
                      title={b.bracket_label}
                    >
                      <div
                        className="bg-boz-primary rounded-sm mx-px"
                        style={{
                          height: `${Math.max(b.probability * 80, 4)}px`,
                        }}
                      />
                      <span className="text-[9px] text-boz-neutral leading-tight block mt-0.5">
                        {Math.round(b.probability * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Active Positions */}
      {data.active_positions.length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">
            Open Positions
          </h2>
          <div className="space-y-2">
            {data.active_positions.map((trade) => (
              <TradeCard key={trade.id} trade={trade} />
            ))}
          </div>
        </section>
      )}

      {/* Recent Trades */}
      {data.recent_trades.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-900 mb-3">
            Recent Trades
          </h2>
          <div className="space-y-2">
            {data.recent_trades.map((trade) => (
              <TradeCard key={trade.id} trade={trade} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function DashboardSkeleton() {
  return (
    <>
      <div className="grid grid-cols-2 gap-3 mb-6">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-6 w-40 mb-3" />
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    </>
  );
}

export default function DashboardPage() {
  const { data, error, isLoading } = useDashboard();

  return (
    <ErrorBoundary>
      <h1 className="text-xl font-bold mb-4">Dashboard</h1>

      {isLoading && <DashboardSkeleton />}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-boz-danger">
          {error.message || "Unable to connect to server"}
        </div>
      )}

      {data && <DashboardContent data={data} />}
    </ErrorBoundary>
  );
}
