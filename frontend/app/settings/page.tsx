"use client";

import { Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { mutate } from "swr";

import ErrorBoundary from "@/components/ui/error-boundary";
import Skeleton from "@/components/ui/skeleton";
import { disconnect, updateSettings } from "@/lib/api";
import { useAuthStatus, useSettings } from "@/lib/hooks";
import type { CityCode, SettingsUpdate, TradingMode } from "@/lib/types";
import { centsToDollars } from "@/lib/utils";

const ALL_CITIES: CityCode[] = ["NYC", "CHI", "MIA", "AUS"];

export default function SettingsPage() {
  const { data: settings, error, isLoading } = useSettings();
  const { data: authStatus } = useAuthStatus();

  // Local form state
  const [tradingMode, setTradingMode] = useState<TradingMode>("manual");
  const [maxTradeSize, setMaxTradeSize] = useState(100);
  const [dailyLossLimit, setDailyLossLimit] = useState(1000);
  const [maxExposure, setMaxExposure] = useState(2500);
  const [minEv, setMinEv] = useState(0.05);
  const [cooldown, setCooldown] = useState(60);
  const [consecutiveLossLimit, setConsecutiveLossLimit] = useState(3);
  const [activeCities, setActiveCities] = useState<CityCode[]>(ALL_CITIES);
  const [notifications, setNotifications] = useState(true);

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  // Sync local state when settings load
  useEffect(() => {
    if (settings) {
      setTradingMode(settings.trading_mode);
      setMaxTradeSize(settings.max_trade_size_cents);
      setDailyLossLimit(settings.daily_loss_limit_cents);
      setMaxExposure(settings.max_daily_exposure_cents);
      setMinEv(settings.min_ev_threshold);
      setCooldown(settings.cooldown_per_loss_minutes);
      setConsecutiveLossLimit(settings.consecutive_loss_limit);
      setActiveCities(settings.active_cities);
      setNotifications(settings.notifications_enabled);
    }
  }, [settings]);

  const toggleCity = (city: CityCode) => {
    setActiveCities((prev) =>
      prev.includes(city)
        ? prev.filter((c) => c !== city)
        : [...prev, city]
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMessage(null);
    try {
      const update: SettingsUpdate = {
        trading_mode: tradingMode,
        max_trade_size_cents: maxTradeSize,
        daily_loss_limit_cents: dailyLossLimit,
        max_daily_exposure_cents: maxExposure,
        min_ev_threshold: minEv,
        cooldown_per_loss_minutes: cooldown,
        consecutive_loss_limit: consecutiveLossLimit,
        active_cities: activeCities,
        notifications_enabled: notifications,
      };
      await updateSettings(update);
      await mutate("/api/settings");
      setSaveMessage("Settings saved!");
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to save settings"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect your Kalshi account? This will delete all your data.")) {
      return;
    }
    setDisconnecting(true);
    try {
      await disconnect();
      window.location.href = "/onboarding";
    } catch (err) {
      alert(err instanceof Error ? err.message : "Disconnect failed");
      setDisconnecting(false);
    }
  };

  if (isLoading) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4">Settings</h1>
        <div className="space-y-4">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4">Settings</h1>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-boz-danger">
          {error.message || "Unable to load settings"}
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <h1 className="text-xl font-bold mb-4">Settings</h1>

      <div className="space-y-6">
        {/* Connection Status */}
        {authStatus && (
          <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <h2 className="text-sm font-semibold mb-3">Connection Status</h2>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-boz-success" />
                <span className="text-sm font-medium">Connected</span>
              </div>
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  authStatus.demo_mode
                    ? "bg-orange-100 text-orange-700"
                    : "bg-green-100 text-green-700"
                }`}
              >
                {authStatus.demo_mode ? "DEMO" : "LIVE"}
              </span>
            </div>
            <p className="text-xs text-boz-neutral mt-2">
              Key: {authStatus.key_id_prefix}
            </p>
          </section>
        )}

        {/* Trading Mode */}
        <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <h2 className="text-sm font-semibold mb-3">Trading Mode</h2>
          <div className="flex gap-2">
            {(["manual", "auto"] as TradingMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setTradingMode(mode)}
                className={`min-h-[44px] flex-1 px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                  tradingMode === mode
                    ? "bg-boz-primary text-white"
                    : "bg-gray-100 text-boz-neutral hover:bg-gray-200"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
          <p className="text-xs text-boz-neutral mt-2">
            {tradingMode === "auto"
              ? "Trades are executed automatically when +EV opportunities are found."
              : "Trades require your approval in the Queue before execution."}
          </p>
        </section>

        {/* Risk Limits */}
        <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <h2 className="text-sm font-semibold mb-3">Risk Limits</h2>
          <div className="space-y-4">
            <div>
              <label className="flex justify-between text-xs mb-1">
                <span>Max Trade Size</span>
                <span className="font-medium">${centsToDollars(maxTradeSize)}</span>
              </label>
              <input
                type="range"
                min={10}
                max={1000}
                step={10}
                value={maxTradeSize}
                onChange={(e) => setMaxTradeSize(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-boz-primary"
              />
            </div>
            <div>
              <label className="flex justify-between text-xs mb-1">
                <span>Daily Loss Limit</span>
                <span className="font-medium">${centsToDollars(dailyLossLimit)}</span>
              </label>
              <input
                type="range"
                min={100}
                max={10000}
                step={100}
                value={dailyLossLimit}
                onChange={(e) => setDailyLossLimit(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-boz-primary"
              />
            </div>
            <div>
              <label className="flex justify-between text-xs mb-1">
                <span>Max Daily Exposure</span>
                <span className="font-medium">${centsToDollars(maxExposure)}</span>
              </label>
              <input
                type="range"
                min={100}
                max={25000}
                step={100}
                value={maxExposure}
                onChange={(e) => setMaxExposure(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-boz-primary"
              />
            </div>
            <div>
              <label className="flex justify-between text-xs mb-1">
                <span>Min EV Threshold</span>
                <span className="font-medium">{(minEv * 100).toFixed(0)}%</span>
              </label>
              <input
                type="range"
                min={0}
                max={0.5}
                step={0.01}
                value={minEv}
                onChange={(e) => setMinEv(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-boz-primary"
              />
            </div>
            <div>
              <label className="flex justify-between text-xs mb-1">
                <span>Cooldown After Loss</span>
                <span className="font-medium">{cooldown} min</span>
              </label>
              <input
                type="range"
                min={0}
                max={1440}
                step={15}
                value={cooldown}
                onChange={(e) => setCooldown(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-boz-primary"
              />
            </div>
            <div>
              <label className="flex justify-between text-xs mb-1">
                <span>Consecutive Loss Limit</span>
                <span className="font-medium">{consecutiveLossLimit}</span>
              </label>
              <input
                type="range"
                min={0}
                max={10}
                step={1}
                value={consecutiveLossLimit}
                onChange={(e) => setConsecutiveLossLimit(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-boz-primary"
              />
            </div>
          </div>
        </section>

        {/* Active Cities */}
        <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <h2 className="text-sm font-semibold mb-3">Active Cities</h2>
          <div className="grid grid-cols-2 gap-2">
            {ALL_CITIES.map((city) => (
              <button
                key={city}
                onClick={() => toggleCity(city)}
                className={`min-h-[44px] px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeCities.includes(city)
                    ? "bg-boz-primary text-white"
                    : "bg-gray-100 text-boz-neutral hover:bg-gray-200"
                }`}
              >
                {city}
              </button>
            ))}
          </div>
        </section>

        {/* Notifications */}
        <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Notifications</h2>
              <p className="text-xs text-boz-neutral">
                Receive push alerts for trades and settlements
              </p>
            </div>
            <button
              onClick={() => setNotifications(!notifications)}
              className={`relative w-12 h-7 rounded-full transition-colors ${
                notifications ? "bg-boz-primary" : "bg-gray-300"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full transition-transform shadow ${
                  notifications ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>
        </section>

        {/* Save */}
        {saveMessage && (
          <div
            className={`text-sm text-center py-2 rounded-lg ${
              saveMessage.includes("saved")
                ? "bg-green-50 text-boz-success"
                : "bg-red-50 text-boz-danger"
            }`}
          >
            {saveMessage}
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="min-h-[44px] w-full px-6 py-3 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {saving ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Save size={16} />
          )}
          {saving ? "Saving..." : "Save Settings"}
        </button>

        {/* Disconnect */}
        <section className="border-t border-gray-200 pt-6">
          <button
            onClick={handleDisconnect}
            disabled={disconnecting}
            className="min-h-[44px] w-full px-6 py-3 bg-white border border-boz-danger text-boz-danger rounded-lg font-medium hover:bg-red-50 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {disconnecting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : null}
            {disconnecting ? "Disconnecting..." : "Disconnect Kalshi Account"}
          </button>
          <p className="text-xs text-boz-neutral text-center mt-2">
            This will delete all stored credentials and trade data.
          </p>
        </section>
      </div>
    </ErrorBoundary>
  );
}
