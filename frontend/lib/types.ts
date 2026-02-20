/**
 * TypeScript interfaces matching the backend Pydantic response schemas.
 *
 * IMPORTANT: Field names match the actual JSON returned by the API,
 * NOT the original CLAUDE.md spec names.
 */

// ─── Literal Types ───

export type CityCode = "NYC" | "CHI" | "MIA" | "AUS";
export type TradeSide = "yes" | "no";
export type ConfidenceLevel = "high" | "medium" | "low";
export type TradeStatus = "OPEN" | "WON" | "LOST" | "CANCELED";
export type PendingTradeStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED"
  | "EXECUTED";
export type TradingMode = "auto" | "manual";

// ─── Auth ───

export interface AuthValidateRequest {
  key_id: string;
  private_key: string;
  demo_mode?: boolean;
}

export interface AuthValidateResponse {
  valid: boolean;
  balance_cents: number;
  demo_mode: boolean;
}

export interface AuthStatusResponse {
  authenticated: boolean;
  user_id: string;
  demo_mode: boolean;
  key_id_prefix: string;
}

// ─── Dashboard ───

export interface DashboardData {
  balance_cents: number;
  today_pnl_cents: number;
  active_positions: TradeRecord[];
  recent_trades: TradeRecord[];
  next_market_launch: string | null;
  predictions: BracketPrediction[];
}

// ─── Trades ───

export interface TradeRecord {
  id: string;
  kalshi_order_id: string | null;
  city: CityCode;
  date: string; // ISO date string YYYY-MM-DD
  market_ticker: string | null;
  bracket_label: string;
  side: TradeSide;
  price_cents: number;
  quantity: number;
  model_probability: number;
  market_probability: number;
  ev_at_entry: number;
  confidence: ConfidenceLevel;
  status: TradeStatus;
  settlement_temp_f: number | null;
  settlement_source: string | null;
  pnl_cents: number | null;
  created_at: string; // ISO datetime string
  settled_at: string | null;
}

export interface TradesPage {
  trades: TradeRecord[];
  total: number;
  page: number;
}

// ─── Pending Trades (Queue) ───

export interface PendingTrade {
  id: string;
  city: CityCode;
  bracket: string;
  market_ticker: string | null;
  side: TradeSide;
  price_cents: number;
  quantity: number;
  model_probability: number;
  market_probability: number;
  ev: number;
  confidence: ConfidenceLevel;
  reasoning: string;
  status: PendingTradeStatus;
  created_at: string;
  expires_at: string;
  acted_at: string | null;
}

// ─── Predictions / Markets ───

export interface BracketProbability {
  bracket_label: string;
  lower_bound_f: number | null;
  upper_bound_f: number | null;
  probability: number;
}

export interface BracketPrediction {
  city: CityCode;
  date: string;
  brackets: BracketProbability[];
  ensemble_mean_f: number;
  ensemble_std_f: number;
  confidence: ConfidenceLevel;
  model_sources: string[];
  generated_at: string;
}

// ─── Settings ───

export interface UserSettings {
  trading_mode: TradingMode;
  max_trade_size_cents: number;
  daily_loss_limit_cents: number;
  max_daily_exposure_cents: number;
  min_ev_threshold: number;
  cooldown_per_loss_minutes: number;
  consecutive_loss_limit: number;
  active_cities: CityCode[];
  notifications_enabled: boolean;
}

export interface SettingsUpdate {
  trading_mode?: TradingMode;
  max_trade_size_cents?: number;
  daily_loss_limit_cents?: number;
  max_daily_exposure_cents?: number;
  min_ev_threshold?: number;
  cooldown_per_loss_minutes?: number;
  consecutive_loss_limit?: number;
  active_cities?: CityCode[];
  notifications_enabled?: boolean;
  demo_mode?: boolean;
}

// ─── Logs ───

export interface LogEntry {
  id: number;
  timestamp: string;
  level: string;
  module: string;
  message: string;
  data: Record<string, unknown> | null;
}

// ─── Performance ───

export interface CumulativePnlPoint {
  date: string;
  cumulative_pnl: number;
}

export interface AccuracyPoint {
  date: string;
  accuracy: number;
}

export interface PerformanceData {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl_cents: number;
  best_trade_pnl_cents: number;
  worst_trade_pnl_cents: number;
  cumulative_pnl: CumulativePnlPoint[];
  pnl_by_city: Record<string, number>;
  accuracy_over_time: AccuracyPoint[];
}

// ─── Notifications ───

export interface PushSubscriptionPayload {
  endpoint: string;
  expirationTime: number | null;
  keys: Record<string, string>;
}
