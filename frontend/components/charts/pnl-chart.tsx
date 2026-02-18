"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CumulativePnlPoint } from "@/lib/types";
import { centsToDollars } from "@/lib/utils";

interface PnlChartProps {
  data: CumulativePnlPoint[];
}

/**
 * Cumulative P&L line chart with $0 reference line.
 * Uses Recharts ResponsiveContainer for mobile/desktop.
 */
export default function PnlChart({ data }: PnlChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-boz-neutral">
        No P&L data yet
      </div>
    );
  }

  // Convert cents to dollars for display
  const chartData = data.map((d) => ({
    date: d.date,
    pnl: d.cumulative_pnl / 100,
  }));

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h3 className="text-sm font-semibold mb-3">Cumulative P&L</h3>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10 }}
            tickFormatter={(d: string) => {
              const parts = d.split("-");
              return `${parts[1]}/${parts[2]}`;
            }}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            formatter={(value: number) => [
              `$${centsToDollars(value * 100)}`,
              "P&L",
            ]}
            labelFormatter={(label: string) => `Date: ${label}`}
          />
          <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
