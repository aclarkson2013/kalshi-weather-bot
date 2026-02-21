import { describe, expect, it } from "vitest";

import { EVENT_TO_SWR_KEYS } from "@/lib/websocket-types";
import type { WebSocketEvent, WebSocketEventType } from "@/lib/websocket-types";

describe("WebSocket types", () => {
  describe("EVENT_TO_SWR_KEYS mapping", () => {
    it("maps trade.executed to dashboard and trades keys", () => {
      expect(EVENT_TO_SWR_KEYS["trade.executed"]).toEqual([
        "/api/dashboard",
        "/api/trades",
      ]);
    });

    it("maps trade.queued to queue and dashboard keys", () => {
      expect(EVENT_TO_SWR_KEYS["trade.queued"]).toEqual([
        "/api/queue",
        "/api/dashboard",
      ]);
    });

    it("maps trade.settled to dashboard, trades, and performance keys", () => {
      expect(EVENT_TO_SWR_KEYS["trade.settled"]).toEqual([
        "/api/dashboard",
        "/api/trades",
        "/api/performance",
      ]);
    });

    it("maps trade.expired to queue key", () => {
      expect(EVENT_TO_SWR_KEYS["trade.expired"]).toEqual(["/api/queue"]);
    });

    it("maps dashboard.update to dashboard key", () => {
      expect(EVENT_TO_SWR_KEYS["dashboard.update"]).toEqual([
        "/api/dashboard",
      ]);
    });

    it("maps prediction.updated to markets key", () => {
      expect(EVENT_TO_SWR_KEYS["prediction.updated"]).toEqual([
        "/api/markets",
      ]);
    });

    it("covers all 7 event types", () => {
      const eventTypes: WebSocketEventType[] = [
        "trade.executed",
        "trade.queued",
        "trade.settled",
        "trade.expired",
        "trade.synced",
        "dashboard.update",
        "prediction.updated",
      ];
      expect(Object.keys(EVENT_TO_SWR_KEYS)).toEqual(eventTypes);
    });
  });

  describe("WebSocketEvent interface", () => {
    it("accepts valid event shape", () => {
      const event: WebSocketEvent = {
        type: "trade.executed",
        timestamp: "2024-01-15T12:00:00Z",
        data: { city: "NYC", bracket: "55-56" },
      };
      expect(event.type).toBe("trade.executed");
      expect(event.data.city).toBe("NYC");
    });

    it("accepts empty data", () => {
      const event: WebSocketEvent = {
        type: "dashboard.update",
        timestamp: "2024-01-15T12:00:00Z",
        data: {},
      };
      expect(event.data).toEqual({});
    });
  });
});
