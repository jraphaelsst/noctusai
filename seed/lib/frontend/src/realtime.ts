/**
 * Realtime client — the browser half of `noctusai_lib.realtime`.
 *
 * WHY THIS EXISTS
 * ---------------
 * Every live surface on this platform polls: the WhatsApp inbox refetches the
 * chat list every 5s and the open thread every 3s, notifications every 30s.
 * Polling is O(clients × interval) load for data that is usually unchanged,
 * and it is *still* not realtime — a message can sit invisible for a full
 * interval. `useWhatsAppChats.ts` has carried a comment naming this exact
 * upgrade ("replace refetchInterval with a socket subscription that calls
 * qc.setQueryData") since it was written. This is that seam, implemented.
 *
 * The transport is SSE over the product's own API, fed by a Redis Stream —
 * see `KB § PATTERNS/common/realtime-sse-bus.md` for why SSE rather than
 * WebSockets or Supabase Realtime.
 *
 * DESIGN
 * ------
 * - ONE connection per scope, shared by every hook consumer, because browsers
 *   cap concurrent connections per origin and each subscriber costs a
 *   server-side stream reader.
 *
 * 🔴 WHY `fetch` AND NOT `EventSource`
 * ------------------------------------
 * `EventSource` cannot send request headers. This platform authenticates with
 * a bearer token, so an `EventSource` reaches the API with no `Authorization`
 * at all — and it did: on 2026-08-25 every `/stream` request in production was
 * answered 401 and the hook's own backoff ladder retried it forever. The
 * WhatsApp inbox and the live-leads feed had therefore never received a single
 * realtime frame, and neither surface polls (`staleTime: Infinity`, no
 * `refetchInterval`, deliberately, because the stream was supposed to patch
 * the cache). A user watched a chat list that could not update.
 *
 * `withCredentials: true` did not help: it sends COOKIES, and the session
 * lives in a bearer token.
 *
 * So the transport is `fetch` + a `ReadableStream` reader, which can carry the
 * header. The two things `EventSource` gives away for free — reconnect and
 * `Last-Event-ID` resume — this hook already implemented itself (the backoff
 * ladder below, and the `since=` cursor), so nothing was lost by dropping it.
 *
 * The token is fetched FRESH on every connect attempt, which means a reconnect
 * after an expiry picks up the refreshed token instead of retrying a dead one.
 * - Events PATCH the query cache (`setQueryData`). They never trigger a
 *   refetch — a refetch would reintroduce exactly the network round trip this
 *   removes.
 * - Reconnect is backed off and resumes from the last event id, so a dropped
 *   connection replays the gap instead of silently losing messages. This is
 *   the whole reason the server uses a Redis Stream rather than pub/sub.
 */
import { useEffect, useRef, useState } from "react";

/** One frame off the stream. `id` is monotonic and sortable (`<ms>-<seq>`). */
export interface RealtimeMessage {
  id: string;
  event: string;
  payload: Record<string, unknown>;
}

export type RealtimeStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface UseRealtimeStreamOptions {
  /**
   * Called for every event except heartbeats. Keep it cheap and idempotent:
   * a resumed connection may redeliver an event the client already applied,
   * and the same event can arrive twice if the server retried a publish.
   */
  onEvent?: (message: RealtimeMessage) => void;
  /**
   * Current bearer token, or `null` when unauthenticated.
   *
   * 🔴 REQUIRED, not optional, and that is the point. An optional auth hook
   * is one a consumer can forget, and forgetting it reproduces exactly the
   * bug this parameter exists to close: a stream that 401s forever while the
   * UI shows no error. Making it required moves the failure from production
   * to the type checker.
   *
   * Called fresh on every connect attempt, so a reconnect after a token
   * refresh uses the new token rather than retrying the expired one.
   */
  getAuthToken: () => Promise<string | null>;
  /** Set false to tear the connection down (e.g. tab/panel not mounted). */
  enabled?: boolean;
  /** Reconnect backoff ceiling. Default 30s. */
  maxBackoffMs?: number;
  /**
   * Named events to listen for, in ADDITION to the defaults.
   *
   * 🔴 Load-bearing: `EventSource` only delivers a named event to a listener
   * registered for that exact name, so an event the server emits and nobody
   * registered is silently invisible — no error, no frame, the UI simply
   * never updates.
   *
   * This is a per-consumer parameter rather than a growing constant in the
   * seed, because the seed must not know any product's event vocabulary. The
   * defaults below are the WhatsApp inbox's names, kept only so that the
   * first consumer keeps working unchanged; a second live surface supplies
   * its own here instead of editing a shared list. (`KB § PATTERNS/architect/
   * seed-canonical-defaults.md` — a default that is really consumer #1's
   * vocabulary silently misroutes consumers #2..N.)
   */
  events?: readonly string[];
}

const HEARTBEAT_EVENT = "heartbeat";
const BASE_BACKOFF_MS = 1_000;
const DEFAULT_MAX_BACKOFF_MS = 30_000;

/**
 * Subscribe to one scope's event stream.
 *
 * `url` must be the fully-qualified stream endpoint for the scope (the caller
 * owns URL construction — this hook is provider-neutral, exactly like the
 * server-side bus).  Passing `null` disables the subscription.
 */
export function useRealtimeStream(
  url: string | null,
  options: UseRealtimeStreamOptions,
): { status: RealtimeStatus; lastEventId: string | null } {
  const {
    onEvent,
    getAuthToken,
    enabled = true,
    maxBackoffMs = DEFAULT_MAX_BACKOFF_MS,
    events,
  } = options;
  // Joined into a primitive so the effect below re-runs when the vocabulary
  // genuinely changes, not on every render that rebuilds the array literal.
  const eventNamesKey = (events ?? []).join(",");

  const [status, setStatus] = useState<RealtimeStatus>("closed");
  const lastEventIdRef = useRef<string | null>(null);
  // Kept in a ref so a caller re-creating the handler inline (the common case)
  // does not tear down and re-open the connection on every render.
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  // Same reason as `onEventRef`: a product passing an inline arrow would
  // otherwise re-open the connection on every render.
  const getAuthTokenRef = useRef(getAuthToken);
  getAuthTokenRef.current = getAuthToken;

  useEffect(() => {
    if (!url || !enabled) {
      setStatus("closed");
      return;
    }

    let controller: AbortController | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let disposed = false;

    /** Names this consumer wants delivered, plus the seed defaults. */
    const wanted = new Set([
      ...REALTIME_EVENT_NAMES,
      ...(eventNamesKey ? eventNamesKey.split(",") : []),
    ]);

    /**
     * Turn one SSE block into a callback.
     *
     * 🔴 The name filter is kept even though `fetch` hands us every frame,
     * unlike `EventSource` which only delivered registered ones. Dropping it
     * would silently widen every consumer's vocabulary to "whatever the
     * server emits", so a server-side event nobody has handled yet would
     * start reaching `onEvent` the day it ships. Same contract, enforced here
     * instead of by the browser.
     */
    const dispatch = (block: string) => {
      let id = "";
      let name = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue; // comment / keep-alive
        const sep = line.indexOf(":");
        const field = sep === -1 ? line : line.slice(0, sep);
        // One optional space after the colon is part of the framing, per spec.
        const value = sep === -1 ? "" : line.slice(sep + 1).replace(/^ /, "");
        if (field === "id") id = value;
        else if (field === "event") name = value;
        else if (field === "data") dataLines.push(value);
      }
      if (id) lastEventIdRef.current = id;
      if (name === HEARTBEAT_EVENT) return; // liveness only, never domain data
      if (!wanted.has(name)) return;

      let payload: Record<string, unknown> = {};
      const raw = dataLines.join("\n");
      if (raw) {
        try {
          payload = JSON.parse(raw);
        } catch {
          // A frame we cannot parse is a real contract break between the two
          // halves. Report it loudly rather than dropping it silently — a
          // silently-ignored frame looks identical to "realtime is broken".
          console.error(
            "[realtime] unparseable frame — server/client contract mismatch",
            { event: name, data: raw },
          );
          return;
        }
      }
      onEventRef.current?.({ id, event: name, payload });
    };

    const scheduleRetry = () => {
      if (disposed) return;
      setStatus("reconnecting");
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** attempt, maxBackoffMs);
      attempt += 1;
      retryTimer = setTimeout(connect, delay);
    };

    async function connect() {
      if (disposed) return;
      setStatus(attempt === 0 ? "connecting" : "reconnecting");

      // Resume from where we left off, so a dropped connection replays the
      // gap instead of silently losing messages. This is the whole reason the
      // server uses a Redis Stream rather than pub/sub.
      const resumeFrom = lastEventIdRef.current;
      const target = resumeFrom
        ? `${url}${url!.includes("?") ? "&" : "?"}since=${encodeURIComponent(resumeFrom)}`
        : url!;

      controller = new AbortController();
      try {
        // Fetched fresh per attempt — a reconnect after an expiry must not
        // replay the dead token.
        const token = await getAuthTokenRef.current();
        if (disposed) return;

        const headers: Record<string, string> = { Accept: "text/event-stream" };
        if (token) headers.Authorization = `Bearer ${token}`;

        const response = await fetch(target, {
          headers,
          signal: controller.signal,
          credentials: "include",
        });

        if (!response.ok || !response.body) {
          // 🔴 Loud, not silent. The predecessor of this code failed exactly
          // here — 401 forever — and said nothing, so a dead stream was
          // indistinguishable from a quiet one.
          console.error(
            "[realtime] stream refused — no events will arrive until this is fixed",
            { url: target, status: response.status },
          );
          scheduleRetry();
          return;
        }

        attempt = 0; // a successful open resets the backoff ladder
        setStatus("open");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (disposed) return;
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // Blocks are separated by a blank line; `\r\n` is tolerated because
          // a proxy may rewrite the framing. The LAST part is whatever came
          // after the final separator — a partial frame — so it goes back in
          // the buffer rather than being dispatched half-read.
          const parts = buffer.split(/\r?\n\r?\n/);
          buffer = parts.pop() ?? "";
          for (const block of parts) {
            if (block.trim()) dispatch(block);
          }
        }
        // A clean end-of-body is still a lost subscription — reconnect.
        scheduleRetry();
      } catch (err) {
        if (disposed) return;
        // An abort is our own teardown, never a failure worth retrying.
        if ((err as { name?: string })?.name === "AbortError") return;
        scheduleRetry();
      }
    }

    void connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      controller?.abort();
      setStatus("closed");
    };
  }, [url, enabled, maxBackoffMs, eventNamesKey]);

  return { status, lastEventId: lastEventIdRef.current };
}

/**
 * DEFAULT event names the client listens for — the WhatsApp inbox's
 * vocabulary, which was this transport's first consumer.
 *
 * 🔴 Do NOT append a new surface's events here. That would make a seed
 * constant grow once per product, which is the hand-maintained-list drift
 * class: the seed would need editing every time a product invents an event,
 * and nothing would fail if someone forgot. Pass
 * `useRealtimeStream(url, { events: [...] })` from the consumer instead.
 *
 * Kept in lockstep with `app/services/whatsapp_realtime.py::WHATSAPP_EVENTS`.
 */
export const REALTIME_EVENT_NAMES = [
  "message.new",
  "message.ack",
  "chat.read",
  "chat.upsert",
  "session.status",
  "heartbeat",
] as const;

export type RealtimeEventName = (typeof REALTIME_EVENT_NAMES)[number];
