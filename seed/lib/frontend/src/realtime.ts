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
 * - ONE `EventSource` per scope, shared by every hook consumer, because
 *   browsers cap concurrent connections per origin and each subscriber costs
 *   a server-side stream reader.
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
  options: UseRealtimeStreamOptions = {},
): { status: RealtimeStatus; lastEventId: string | null } {
  const {
    onEvent,
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

  useEffect(() => {
    if (!url || !enabled) {
      setStatus("closed");
      return;
    }

    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus(attempt === 0 ? "connecting" : "reconnecting");

      // Resume from where we left off. EventSource sends `Last-Event-ID`
      // automatically on ITS OWN reconnects, but not when we construct a new
      // one after an error — so the cursor rides in the query string too.
      const resumeFrom = lastEventIdRef.current;
      const target = resumeFrom
        ? `${url}${url.includes("?") ? "&" : "?"}since=${encodeURIComponent(resumeFrom)}`
        : url;

      source = new EventSource(target, { withCredentials: true });

      source.onopen = () => {
        if (disposed) return;
        attempt = 0; // a successful open resets the backoff ladder
        setStatus("open");
      };

      const handle = (evt: MessageEvent) => {
        if (disposed) return;
        if (evt.lastEventId) lastEventIdRef.current = evt.lastEventId;

        const name = evt.type || "message";
        if (name === HEARTBEAT_EVENT) return; // liveness only, never domain data

        let payload: Record<string, unknown> = {};
        if (evt.data) {
          try {
            payload = JSON.parse(evt.data as string);
          } catch {
            // A frame we cannot parse is a real contract break between the two
            // halves. Report it loudly rather than dropping it silently — a
            // silently-ignored frame looks identical to "realtime is broken".
            console.error(
              "[realtime] unparseable frame — server/client contract mismatch",
              { event: name, data: evt.data },
            );
            return;
          }
        }
        onEventRef.current?.({ id: evt.lastEventId || "", event: name, payload });
      };

      // Named events do NOT fire `onmessage` — each must be registered.
      // Anything the server can emit has to be registered here or it is
      // invisible. `Set` because a consumer naming an event that is also a
      // default would otherwise attach the same handler twice and apply the
      // event twice.
      source.onmessage = handle;
      for (const name of new Set([
        ...REALTIME_EVENT_NAMES,
        ...(eventNamesKey ? eventNamesKey.split(",") : []),
      ])) {
        source.addEventListener(name, handle as EventListener);
      }

      source.onerror = () => {
        if (disposed) return;
        source?.close();
        source = null;
        setStatus("reconnecting");
        const delay = Math.min(BASE_BACKOFF_MS * 2 ** attempt, maxBackoffMs);
        attempt += 1;
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      source?.close();
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
