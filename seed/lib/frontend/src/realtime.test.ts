/**
 * `useRealtimeStream` — the transport that had never delivered a frame.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Until 2026-08-25 this hook opened an `EventSource`. `EventSource` cannot
 * send request headers, this platform authenticates with a bearer token, and
 * so every `/stream` request in production was answered 401 — forever, on the
 * hook's own backoff ladder, with nothing on screen to say so. The WhatsApp
 * inbox and the live-leads feed both gate on `staleTime: Infinity` with no
 * `refetchInterval`, deliberately, because the stream was supposed to patch
 * their caches. Neither had ever updated.
 *
 * There was no test here at all, and that is the actual finding: the hook was
 * only ever exercised through consumers that MOCKED it, so nothing anywhere
 * asserted that a real connection could authenticate or that a real frame
 * could be parsed. These tests are that missing floor.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

import { useRealtimeStream } from "./realtime";

/** Build a Response-like object whose body yields `chunks`, then ends. */
function streamingResponse(chunks: string[], { ok = true, status = 200 } = {}) {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    ok,
    status,
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length
            ? { done: false, value: encoder.encode(chunks[i++]) }
            : { done: true, value: undefined },
      }),
    },
  };
}

const token = vi.fn(async () => "jwt-abc");

beforeEach(() => {
  token.mockClear();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useRealtimeStream — authentication", () => {
  it("sends the bearer token, which is the whole reason it is not an EventSource", async () => {
    (globalThis.fetch as any).mockResolvedValue(streamingResponse([]));

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token }),
    );

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const [, init] = (globalThis.fetch as any).mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer jwt-abc");
    expect(init.headers.Accept).toBe("text/event-stream");
  });

  it("omits the header rather than sending 'Bearer null' when unauthenticated", async () => {
    (globalThis.fetch as any).mockResolvedValue(streamingResponse([]));

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: async () => null }),
    );

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const [, init] = (globalThis.fetch as any).mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("re-reads the token on every attempt, so a reconnect after expiry uses the fresh one", async () => {
    let n = 0;
    const rotating = vi.fn(async () => `jwt-${n++}`);
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([], { ok: false, status: 401 }),
    );
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.useFakeTimers();

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: rotating }),
    );

    await vi.waitFor(() => expect(rotating).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(rotating.mock.calls.length).toBeGreaterThan(1);
    vi.useRealTimers();
  });

  it("says so loudly when the stream is refused", async () => {
    // 🔴 The predecessor failed exactly here and said nothing, so a dead
    // stream looked identical to a quiet one for months.
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([], { ok: false, status: 401 }),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token }),
    );

    await waitFor(() => expect(err).toHaveBeenCalled());
    expect(String(err.mock.calls[0][0])).toContain("stream refused");
  });
});

describe("useRealtimeStream — frame parsing", () => {
  it("delivers a named event with its payload and id", async () => {
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([
        'id: 17-0\nevent: message.new\ndata: {"chat":"abc"}\n\n',
      ]),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(onEvent.mock.calls[0][0]).toEqual({
      id: "17-0",
      event: "message.new",
      payload: { chat: "abc" },
    });
  });

  it("reassembles a frame split across chunks", async () => {
    // A real socket splits wherever it likes; a parser that assumes one read
    // per frame drops messages under exactly the load it matters at.
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([
        "id: 1-0\nevent: message",
        '.new\ndata: {"half":',
        '"two"}\n\n',
      ]),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(onEvent.mock.calls[0][0].payload).toEqual({ half: "two" });
  });

  it("delivers both frames when two arrive in one chunk", async () => {
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([
        'id: 1-0\nevent: message.new\ndata: {"n":1}\n\n' +
          'id: 2-0\nevent: message.new\ndata: {"n":2}\n\n',
      ]),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(2));
    expect(onEvent.mock.calls.map((c) => c[0].payload)).toEqual([
      { n: 1 },
      { n: 2 },
    ]);
  });

  it("swallows heartbeats — liveness is not domain data", async () => {
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([
        "id: 1-0\nevent: heartbeat\ndata: {}\n\n",
        'id: 2-0\nevent: message.new\ndata: {"real":true}\n\n',
      ]),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent.mock.calls[0][0].event).toBe("message.new");
  });

  it("ignores an event this consumer never registered", async () => {
    // `EventSource` enforced this in the browser. `fetch` hands us everything,
    // so the filter has to live in the hook — otherwise a server-side event
    // nobody has handled yet starts reaching `onEvent` the day it ships.
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse(['id: 1-0\nevent: nobody.asked\ndata: {"x":1}\n\n']),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("delivers a consumer's own declared vocabulary", async () => {
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse(['id: 1-0\nevent: lead.new\ndata: {"id":"L1"}\n\n']),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", {
        getAuthToken: token,
        onEvent,
        events: ["lead.new"],
      }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(onEvent.mock.calls[0][0].event).toBe("lead.new");
  });

  it("reports an unparseable frame instead of dropping it silently", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse(["id: 1-0\nevent: message.new\ndata: {not json\n\n"]),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(err).toHaveBeenCalled());
    expect(String(err.mock.calls[0][0])).toContain("unparseable frame");
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("skips comment lines a proxy may inject as keep-alive", async () => {
    const onEvent = vi.fn();
    (globalThis.fetch as any).mockResolvedValue(
      streamingResponse([
        ': keep-alive\nid: 1-0\nevent: message.new\ndata: {"ok":true}\n\n',
      ]),
    );

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(onEvent.mock.calls[0][0].payload).toEqual({ ok: true });
  });
});

describe("useRealtimeStream — lifecycle", () => {
  it("opens nothing when url is null", async () => {
    renderHook(() => useRealtimeStream(null, { getAuthToken: token }));
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(token).not.toHaveBeenCalled();
  });

  it("opens nothing when disabled", async () => {
    renderHook(() =>
      useRealtimeStream("/api/x/stream", {
        getAuthToken: token,
        enabled: false,
      }),
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("resumes from the last event id it saw", async () => {
    // The cursor is why the server uses a Redis Stream rather than pub/sub: a
    // dropped connection must replay the gap, not skip it.
    const onEvent = vi.fn();
    (globalThis.fetch as any)
      .mockResolvedValueOnce(
        streamingResponse(['id: 42-0\nevent: message.new\ndata: {}\n\n']),
      )
      .mockResolvedValue(streamingResponse([]));
    vi.useFakeTimers();

    renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token, onEvent }),
    );

    await vi.waitFor(() => expect(onEvent).toHaveBeenCalled());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    const urls = (globalThis.fetch as any).mock.calls.map((c: any[]) => c[0]);
    expect(urls.some((u: string) => u.includes("since=42-0"))).toBe(true);
    vi.useRealTimers();
  });

  it("aborts the request on unmount rather than leaking a reader", async () => {
    (globalThis.fetch as any).mockResolvedValue(streamingResponse([]));

    const { unmount } = renderHook(() =>
      useRealtimeStream("/api/x/stream", { getAuthToken: token }),
    );
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const [, init] = (globalThis.fetch as any).mock.calls[0];
    expect(init.signal.aborted).toBe(false);

    unmount();

    expect(init.signal.aborted).toBe(true);
  });
});
