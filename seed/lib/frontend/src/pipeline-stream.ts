/**
 * `usePipelineStream` — a kanban board kept live over SSE, polling only as the fallback.
 *
 * Browser half of `noctusai_lib.domain.pipeline.stream` (`pipeline.card_moved` / `pipeline.card_state` on
 * scope `pipeline:{org}:{pipeline}`). Each frame is merged into the TanStack cache entries holding the board
 * (`setQueryData`, never a refetch). Server-state rules: an entry that is not loaded yet is left untouched
 * (never invent a board while loading); a card the entry does not contain is not fabricated (the next read
 * brings it); every listed entry the event touches is filled, not just the first.
 *
 * When the stream is not open for `fallbackAfterMs` the hook invalidates `queryKeys` every `pollMs`
 * (the board's own reads re-fetch); on (re)open it invalidates once to close any gap before resume.
 *
 * ```ts
 * usePipelineStream("esteira", {
 *   url: `/api/esteira/stream`, getAuthToken, queryKeys: [["esteira", "board"]],
 * });
 * ```
 */
import { useEffect, useRef } from "react";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";

import { useRealtimeStream, type RealtimeMessage, type RealtimeStatus } from "./realtime";

export const PIPELINE_CARD_MOVED_EVENT = "pipeline.card_moved";
export const PIPELINE_CARD_STATE_EVENT = "pipeline.card_state";
export const PIPELINE_STREAM_FALLBACK_MS = 8_000;
export const PIPELINE_STREAM_POLL_MS = 5_000;

export interface PipelineCardMoved {
  card_id: string;
  from_stage_id: string | null;
  to_stage_id: string;
  motivo: string | null;
  actor: string | null;
  at: string;
}

export interface PipelineCardState {
  card_id: string;
  state: Record<string, unknown>;
}

export interface PipelineStreamAccessors<TCard = any> {
  /** Default `c.id`. */
  getCardId?: (card: TCard) => string;
  /** Default: sets `etapa_id`. */
  withStage?: (card: TCard, stageId: string) => TCard;
  /** Default: shallow-merges the state into the card. */
  withState?: (card: TCard, state: Record<string, unknown>) => TCard;
}

export interface UsePipelineStreamOptions<TCard = any> extends PipelineStreamAccessors<TCard> {
  /** Fully-qualified stream endpoint; `null` disables the hook. */
  url: string | null;
  getAuthToken: () => Promise<string | null>;
  /** Cache entries holding the board: each an array of cards, or an object with a `cards` array. */
  queryKeys: QueryKey[];
  enabled?: boolean;
  fallbackAfterMs?: number;
  pollMs?: number;
}

const defaultId = (c: any): string => c.id;
const defaultStage = (c: any, stageId: string) => ({ ...c, etapa_id: stageId });
const defaultState = (c: any, state: Record<string, unknown>) => ({ ...c, ...state });

/**
 * Fold one frame into a cached board value (array of cards, or `{ cards: [...] }`). Pure; returns `prev`
 * (same reference) when there is nothing to change, so React Query skips the notification.
 */
export function applyPipelineEvent<TData>(
  prev: TData | undefined,
  message: Pick<RealtimeMessage, "event" | "payload">,
  accessors: PipelineStreamAccessors = {},
): TData | undefined {
  if (prev == null) return prev; // still loading: never invent a board
  const getId = accessors.getCardId ?? defaultId;
  let change: (card: any) => any;
  let cardId: string;
  if (message.event === PIPELINE_CARD_MOVED_EVENT) {
    const p = message.payload as unknown as PipelineCardMoved;
    cardId = p.card_id;
    const withStage = accessors.withStage ?? defaultStage;
    change = (c) => withStage(c, p.to_stage_id);
  } else if (message.event === PIPELINE_CARD_STATE_EVENT) {
    const p = message.payload as unknown as PipelineCardState;
    cardId = p.card_id;
    const withState = accessors.withState ?? defaultState;
    change = (c) => withState(c, p.state ?? {});
  } else {
    return prev;
  }
  const patch = (cards: any[]): any[] => {
    let touched = false;
    const next = cards.map((c) => {
      if (getId(c) !== cardId) return c;
      touched = true;
      return change(c);
    });
    return touched ? next : cards;
  };
  if (Array.isArray(prev)) {
    const next = patch(prev);
    return (next === prev ? prev : next) as unknown as TData;
  }
  const cards = (prev as any).cards;
  if (Array.isArray(cards)) {
    const next = patch(cards);
    return next === cards ? prev : ({ ...(prev as any), cards: next } as TData);
  }
  return prev;
}

export function usePipelineStream<TCard = any>(
  pipelineId: string | null,
  options: UsePipelineStreamOptions<TCard>,
): { status: RealtimeStatus; polling: boolean } {
  const { url, getAuthToken, queryKeys, enabled = true, fallbackAfterMs = PIPELINE_STREAM_FALLBACK_MS, pollMs = PIPELINE_STREAM_POLL_MS } = options;
  const qc = useQueryClient();
  const accessorsRef = useRef<PipelineStreamAccessors>(options);
  accessorsRef.current = options;
  const keysRef = useRef(queryKeys);
  keysRef.current = queryKeys;
  const keysHash = JSON.stringify(queryKeys);
  const active = !!pipelineId && !!url && enabled;

  const { status } = useRealtimeStream(active ? url : null, {
    getAuthToken,
    events: [PIPELINE_CARD_MOVED_EVENT, PIPELINE_CARD_STATE_EVENT],
    onEvent: (message) => {
      for (const queryKey of keysRef.current) {
        qc.setQueryData(queryKey, (prev: unknown) => applyPipelineEvent(prev, message, accessorsRef.current));
      }
    },
  });

  const invalidateAll = () => {
    for (const queryKey of keysRef.current) void qc.invalidateQueries({ queryKey });
  };

  // Close any gap on (re)connect.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (status === "open") {
      if (wasOpen.current === false) invalidateAll();
      wasOpen.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, keysHash]);

  // Stream cannot be kept: poll the board reads until it is back.
  const down = active && status !== "open";
  const pollingRef = useRef(false);
  useEffect(() => {
    if (!down) {
      pollingRef.current = false;
      return;
    }
    let interval: ReturnType<typeof setInterval> | undefined;
    const start = setTimeout(() => {
      pollingRef.current = true;
      invalidateAll();
      // poll-budget: 5s while the stream is DOWN only; 2 calls/tick (one per board key); worst 34560/day per open tab; hidden=paused
      interval = setInterval(() => {
        if (typeof document !== "undefined" && document.hidden) return;
        invalidateAll();
      }, pollMs);
    }, fallbackAfterMs);
    return () => {
      clearTimeout(start);
      if (interval) clearInterval(interval);
      pollingRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [down, fallbackAfterMs, pollMs, keysHash]);

  return { status, polling: down && pollingRef.current };
}
