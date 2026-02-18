"use client";

import type { BracketPrediction } from "@/lib/types";
import { formatProbability } from "@/lib/utils";

interface BracketViewProps {
  prediction: BracketPrediction;
  /** Optional market prices (bracket_label → market probability) for EV comparison */
  marketPrices?: Record<string, number>;
}

/**
 * Horizontal bar chart showing model probability vs market probability
 * for each bracket. Blue = model, gray = market, +EV/-EV indicator.
 */
export default function BracketView({
  prediction,
  marketPrices,
}: BracketViewProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold">
            {prediction.city} — High Temp Brackets
          </h3>
          <p className="text-xs text-boz-neutral">
            Mean: {prediction.ensemble_mean_f.toFixed(1)}°F | Std:{" "}
            {prediction.ensemble_std_f.toFixed(1)}°F | Confidence:{" "}
            {prediction.confidence}
          </p>
        </div>
        <span className="text-xs text-boz-neutral">
          {prediction.model_sources.join(", ")}
        </span>
      </div>

      <div className="space-y-2">
        {prediction.brackets.map((bracket) => {
          const marketProb = marketPrices?.[bracket.bracket_label];
          const hasMarket = marketProb !== undefined;
          const ev = hasMarket
            ? bracket.probability - marketProb
            : null;
          const maxProb = Math.max(
            bracket.probability,
            marketProb ?? 0,
            0.01
          );

          return (
            <div key={bracket.bracket_label} className="text-xs">
              {/* Label row */}
              <div className="flex items-center justify-between mb-0.5">
                <span className="font-medium w-20 truncate">
                  {bracket.bracket_label}
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-boz-primary">
                    {formatProbability(bracket.probability)}
                  </span>
                  {hasMarket && (
                    <span className="text-boz-neutral">
                      vs {formatProbability(marketProb)}
                    </span>
                  )}
                  {ev !== null && (
                    <span
                      className={`font-medium px-1 rounded ${
                        ev > 0
                          ? "text-boz-success bg-green-50"
                          : "text-boz-danger bg-red-50"
                      }`}
                    >
                      {ev > 0 ? "+" : ""}
                      {(ev * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>

              {/* Bar */}
              <div className="relative h-4 bg-gray-100 rounded overflow-hidden">
                {/* Market bar (gray, behind) */}
                {hasMarket && (
                  <div
                    className="absolute inset-y-0 left-0 bg-gray-300 rounded"
                    style={{
                      width: `${(marketProb / maxProb) * 100}%`,
                    }}
                  />
                )}
                {/* Model bar (blue, in front) */}
                <div
                  className="absolute inset-y-0 left-0 bg-boz-primary rounded opacity-80"
                  style={{
                    width: `${(bracket.probability / maxProb) * 100}%`,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 text-xs text-boz-neutral">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-boz-primary rounded opacity-80" />
          Model
        </div>
        {marketPrices && (
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 bg-gray-300 rounded" />
            Market
          </div>
        )}
      </div>
    </div>
  );
}
