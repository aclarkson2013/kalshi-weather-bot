"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CITY_NAMES } from "@/lib/utils";

interface CityPerformanceChartProps {
  /** P&L by city in cents: { "NYC": 500, "CHI": -200, ... } */
  pnlByCity: Record<string, number>;
}

/**
 * Bar chart showing P&L per city. Green for positive, red for negative.
 */
export default function CityPerformanceChart({
  pnlByCity,
}: CityPerformanceChartProps) {
  const chartData = Object.entries(pnlByCity).map(([city, pnl]) => ({
    city: CITY_NAMES[city as keyof typeof CITY_NAMES] || city,
    pnl: pnl / 100, // cents to dollars
    raw: pnl,
  }));

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-boz-neutral">
        No city data yet
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h3 className="text-sm font-semibold mb-3">P&L by City</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="city" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 10 }}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            formatter={(value: number) => [
              `$${value.toFixed(2)}`,
              "P&L",
            ]}
          />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.raw >= 0 ? "#16a34a" : "#dc2626"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
