/**
 * WebSocket event types matching the backend event model.
 *
 * These types define the shape of real-time events pushed from
 * the FastAPI server through the WebSocket connection.
 */

// ─── Event Type Literals ───

export type WebSocketEventType =
  | "trade.executed"
  | "trade.queued"
  | "trade.settled"
  | "trade.expired"
  | "trade.synced"
  | "dashboard.update"
  | "prediction.updated";

// ─── Event Interface ───

export interface WebSocketEvent {
  type: WebSocketEventType;
  timestamp: string; // ISO 8601 datetime
  data: Record<string, unknown>;
}

// ─── Event-to-SWR Key Mapping ───

/**
 * Maps each WebSocket event type to the SWR cache keys that should
 * be revalidated when that event is received. This is how real-time
 * events trigger UI updates without replacing SWR as the data layer.
 */
export const EVENT_TO_SWR_KEYS: Record<WebSocketEventType, string[]> = {
  "trade.executed": ["/api/dashboard", "/api/trades"],
  "trade.queued": ["/api/queue", "/api/dashboard"],
  "trade.settled": ["/api/dashboard", "/api/trades", "/api/performance"],
  "trade.expired": ["/api/queue"],
  "trade.synced": ["/api/dashboard", "/api/trades"],
  "dashboard.update": ["/api/dashboard"],
  "prediction.updated": ["/api/markets"],
};
