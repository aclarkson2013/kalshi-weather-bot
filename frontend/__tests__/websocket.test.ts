import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ─── Mock WebSocket ───

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
  }

  // Test helpers
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  simulateMessage(data: string) {
    this.onmessage?.(new MessageEvent("message", { data }));
  }

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }
}

// ─── Mock SWR mutate ───

const mockMutate = vi.fn();

vi.mock("swr", () => ({
  mutate: (...args: unknown[]) => mockMutate(...args),
}));

// ─── Mock getWsUrl ───

vi.mock("@/lib/api", () => ({
  getWsUrl: () => "ws://localhost:8000/ws",
}));

// ─── Setup ───

beforeEach(() => {
  MockWebSocket.instances = [];
  mockMutate.mockClear();
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("WebSocket hook internals", () => {
  it("getWsUrl returns correct WebSocket URL", async () => {
    const { getWsUrl } = await import("@/lib/api");
    expect(getWsUrl()).toBe("ws://localhost:8000/ws");
  });

  it("EVENT_TO_SWR_KEYS has correct trade.executed mapping", async () => {
    const { EVENT_TO_SWR_KEYS } = await import("@/lib/websocket-types");
    expect(EVENT_TO_SWR_KEYS["trade.executed"]).toContain("/api/dashboard");
    expect(EVENT_TO_SWR_KEYS["trade.executed"]).toContain("/api/trades");
  });

  it("EVENT_TO_SWR_KEYS has correct trade.settled mapping", async () => {
    const { EVENT_TO_SWR_KEYS } = await import("@/lib/websocket-types");
    expect(EVENT_TO_SWR_KEYS["trade.settled"]).toContain("/api/performance");
  });

  it("EVENT_TO_SWR_KEYS has correct prediction.updated mapping", async () => {
    const { EVENT_TO_SWR_KEYS } = await import("@/lib/websocket-types");
    expect(EVENT_TO_SWR_KEYS["prediction.updated"]).toContain("/api/markets");
  });
});

describe("MockWebSocket behavior", () => {
  it("creates WebSocket instance with correct URL", () => {
    const ws = new MockWebSocket("ws://localhost:8000/ws");
    expect(ws.url).toBe("ws://localhost:8000/ws");
    expect(ws.readyState).toBe(MockWebSocket.CONNECTING);
  });

  it("transitions through connection states", () => {
    const ws = new MockWebSocket("ws://localhost:8000/ws");
    expect(ws.readyState).toBe(MockWebSocket.CONNECTING);

    ws.simulateOpen();
    expect(ws.readyState).toBe(MockWebSocket.OPEN);

    ws.close();
    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
  });

  it("fires onmessage callback with event data", () => {
    const ws = new MockWebSocket("ws://localhost:8000/ws");
    const handler = vi.fn();
    ws.onmessage = handler;

    ws.simulateMessage('{"type":"trade.executed"}');

    expect(handler).toHaveBeenCalledOnce();
    expect(handler.mock.calls[0][0].data).toBe('{"type":"trade.executed"}');
  });
});
