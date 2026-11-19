/**
 * usePipelineStream — merges `pipeline.card_moved` / `pipeline.card_state` into the board cache, never
 * invents a board while loading, and falls back to polling (invalidation) when the stream is down.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { applyPipelineEvent, usePipelineStream } from "./pipeline-stream";

type Card = { id: string; etapa_id: string; status?: string };
const KEY_A = ["board", "a"] as const;
const KEY_B = ["board", "b"] as const;

const movedPayload = (card_id: string, to: string) => ({
  card_id, from_stage_id: "s1", to_stage_id: to, motivo: null, actor: "u", at: "t",
});
const moved = (card_id: string, to: string) => ({ event: "pipeline.card_moved", payload: movedPayload(card_id, to) });
const state = (card_id: string, s: Record<string, unknown>) => ({
  event: "pipeline.card_state",
  payload: { card_id, state: s },
});

describe("applyPipelineEvent", () => {
  const board: Card[] = [{ id: "c1", etapa_id: "s1" }, { id: "c2", etapa_id: "s1" }];

  it("moves only the named card", () => {
    const next = applyPipelineEvent(board, moved("c1", "s2")) as Card[];
    expect(next.map((c) => c.etapa_id)).toEqual(["s2", "s1"]);
    expect(next[1]).toBe(board[1]);
  });

  it("merges card state", () => {
    const next = applyPipelineEvent(board, state("c2", { status: "Gerando" })) as Card[];
    expect(next[1]).toEqual({ id: "c2", etapa_id: "s1", status: "Gerando" });
  });

  it("does not invent a board while loading, nor a missing card", () => {
    expect(applyPipelineEvent(undefined, moved("c1", "s2"))).toBeUndefined();
    expect(applyPipelineEvent(board, moved("zz", "s2"))).toBe(board);
  });

  it("handles { cards } shapes and custom accessors; ignores unknown events", () => {
    const wrapped = { cards: [{ id: "c1", stage: "s1" }], total: 1 };
    const next = applyPipelineEvent(wrapped, moved("c1", "s9"), {
      withStage: (c: any, s: string) => ({ ...c, stage: s }),
    }) as typeof wrapped;
    expect(next.cards[0].stage).toBe("s9");
    expect(next.total).toBe(1);
    expect(applyPipelineEvent(board, { event: "job.progress", payload: {} })).toBe(board);
  });
});

function sse(frames: string[], opts: { hang?: boolean; ok?: boolean; status?: number } = {}) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: opts.ok ?? true,
    status: opts.status ?? 200,
    body: {
      getReader: () => ({
        read: async () => {
          if (i < frames.length) return { done: false, value: enc.encode(frames[i++]) };
          if (opts.hang) return new Promise(() => {});
          return { done: true, value: undefined };
        },
      }),
    },
  };
}
const frame = (event: string, payload: object) => `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;

let qc: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: qc }, children);

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal("fetch", vi.fn());
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("usePipelineStream", () => {
  it("fills every listed cache entry and leaves an unloaded one untouched", async () => {
    qc.setQueryData(KEY_A, [{ id: "c1", etapa_id: "s1" }]);
    // KEY_B deliberately not loaded
    (fetch as any).mockResolvedValue(
      sse(
        [
          frame("pipeline.card_moved", movedPayload("c1", "s2")),
          frame("pipeline.card_state", { card_id: "c1", state: { status: "ok" } }),
        ],
        { hang: true },
      ),
    );
    renderHook(
      () => usePipelineStream("esteira", { url: "/api/x/stream", getAuthToken: async () => "t", queryKeys: [KEY_A, KEY_B] }),
      { wrapper },
    );
    await waitFor(() => expect((qc.getQueryData(KEY_A) as Card[])[0].status).toBe("ok"));
    expect((qc.getQueryData(KEY_A) as Card[])[0].etapa_id).toBe("s2");
    expect(qc.getQueryData(KEY_B)).toBeUndefined();
  });

  it("falls back to invalidating the board reads when the stream is refused", async () => {
    qc.setQueryData(KEY_A, []);
    const spy = vi.spyOn(qc, "invalidateQueries");
    (fetch as any).mockResolvedValue(sse([], { ok: false, status: 401 }));
    renderHook(
      () =>
        usePipelineStream("esteira", {
          url: "/api/x/stream", getAuthToken: async () => "t", queryKeys: [KEY_A], fallbackAfterMs: 30, pollMs: 30,
        }),
      { wrapper },
    );
    await waitFor(() => expect(spy).toHaveBeenCalled(), { timeout: 2000 });
  });

  it("is idle when disabled", () => {
    renderHook(() => usePipelineStream(null, { url: null, getAuthToken: async () => null, queryKeys: [KEY_A] }), { wrapper });
    expect(fetch).not.toHaveBeenCalled();
  });
});
