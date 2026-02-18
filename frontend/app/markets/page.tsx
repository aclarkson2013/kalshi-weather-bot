"use client";

import { BarChart3 } from "lucide-react";
import { useState } from "react";

import BracketView from "@/components/bracket-view/bracket-view";
import EmptyState from "@/components/ui/empty-state";
import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import { useMarkets } from "@/lib/hooks";
import type { CityCode } from "@/lib/types";

const CITIES: (CityCode | "ALL")[] = ["ALL", "NYC", "CHI", "MIA", "AUS"];

export default function MarketsPage() {
  const [selectedCity, setSelectedCity] = useState<CityCode | "ALL">("ALL");
  const cityFilter = selectedCity === "ALL" ? undefined : selectedCity;
  const { data, error, isLoading } = useMarkets(cityFilter);

  return (
    <ErrorBoundary>
      <h1 className="text-xl font-bold mb-4">Markets</h1>

      {/* City filter tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto">
        {CITIES.map((city) => (
          <button
            key={city}
            onClick={() => setSelectedCity(city)}
            className={`min-h-[44px] px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              selectedCity === city
                ? "bg-boz-primary text-white"
                : "bg-white border border-gray-200 text-boz-neutral hover:bg-gray-50"
            }`}
          >
            {city === "ALL" ? "All Cities" : city}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-boz-danger">
          {error.message || "Unable to load markets"}
        </div>
      )}

      {data && data.length === 0 && (
        <EmptyState
          icon={BarChart3}
          title="No Predictions Available"
          description="Predictions are generated daily. Check back after the morning model run."
        />
      )}

      {data && data.length > 0 && (
        <div className="space-y-4">
          {data.map((prediction) => (
            <BracketView key={prediction.city} prediction={prediction} />
          ))}
        </div>
      )}
    </ErrorBoundary>
  );
}
