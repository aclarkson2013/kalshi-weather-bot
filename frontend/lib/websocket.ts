"use client";

/**
 * WebSocket client — real-time event streaming with SWR revalidation.
 *
 * Architecture:
 *   Browser WebSocket ← FastAPI /ws ← Redis pub/sub ← Celery tasks
 *
 * On each event, the hook looks up which SWR cache keys to revalidate
 * via EVENT_TO_SWR_KEYS, then calls mutate() to trigger re-fetches.
 * SWR remains the data layer; WebSocket only signals "something changed".
 *
 * Reconnection uses exponential backoff (1s → 2s → 4s → ... → 30s max).
 * If the WebSocket disconnects, SWR polling continues as fallback.
 */

import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { mutate } from "swr";

import { getWsUrl } from "./api";
import type { WebSocketEvent, WebSocketEventType } from "./websocket-types";
import { EVENT_TO_SWR_KEYS } from "./websocket-types";

// ─── Constants ───

const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;
const BACKOFF_MULTIPLIER = 2;

// ─── Context ───

interface WebSocketContextValue {
  isConnected: boolean;
}

const WebSocketContext = createContext<WebSocketContextValue>({
  isConnected: false,
});

export function useWebSocketStatus(): WebSocketContextValue {
  return useContext(WebSocketContext);
}

// ─── Hook ───

/**
 * Core WebSocket hook. Manages connection lifecycle, reconnection
 * with exponential backoff, and SWR cache revalidation on events.
 */
export function useWebSocket(): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelayRef = useRef(INITIAL_RETRY_MS);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const revalidateForEvent = useCallback((eventType: string) => {
    const keys = EVENT_TO_SWR_KEYS[eventType as WebSocketEventType];
    if (!keys) return;

    for (const key of keys) {
      // mutate with key prefix match — revalidates all SWR hooks
      // whose key starts with this prefix (e.g., "/api/trades" matches
      // "/api/trades?page=1&city=NYC")
      mutate(
        (swrKey: string) => typeof swrKey === "string" && swrKey.startsWith(key),
        undefined,
        { revalidate: true }
      );
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Don't reconnect if already open
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = getWsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setIsConnected(true);
      retryDelayRef.current = INITIAL_RETRY_MS;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return;

      try {
        const parsed: WebSocketEvent = JSON.parse(event.data);
        revalidateForEvent(parsed.type);
      } catch {
        // Malformed message — ignore
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setIsConnected(false);
      wsRef.current = null;

      // Schedule reconnection with exponential backoff
      const delay = retryDelayRef.current;
      retryDelayRef.current = Math.min(
        delay * BACKOFF_MULTIPLIER,
        MAX_RETRY_MS
      );
      retryTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnection handled there
      ws.close();
    };
  }, [revalidateForEvent]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;

      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }

      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected };
}

// ─── Provider ───

/**
 * Wraps the app to provide a single shared WebSocket connection.
 * Must be rendered inside a "use client" boundary.
 */
export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { isConnected } = useWebSocket();

  return createElement(
    WebSocketContext.Provider,
    { value: { isConnected } },
    children
  );
}
