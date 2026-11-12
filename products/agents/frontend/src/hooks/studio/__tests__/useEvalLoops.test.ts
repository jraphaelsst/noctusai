/** useEvalLoops.ts — list/detail polling, create/stop cache writes (the server's LoopOut lands in the cache), round start. */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const wrapper = (qc: QueryClient) => ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: qc }, children);
const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

function loop(over: Record<string, unknown> = {}) {
  return {
    id: "l1", agente_chave: "isaia", suite: "comportamento", status: "ativo", motivo_parada: null, detalhe_parada: null,
    rodadas_planejadas: 30, rodadas_feitas: 0, alvo: 1, piso: 0.8, orcamento_usd: 20, gasto_usd: 0, restante_usd: 20,
    melhor_score: null, score_atual: null, acima_do_piso: null, started_at: "2026-11-12T00:00:00Z", stopped_at: null,
    serie: [], overcalls: [], custo_overcalls_usd: 0, checkpoints: [], ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("useEvalLoops", () => {
  it("GETs the loops, filtered by suite", async () => {
    mockGet.mockResolvedValue({ items: [loop()] });
    const { useEvalLoops } = await import("@/hooks/studio/useEvalLoops");
    const { result } = renderHook(() => useEvalLoops("isaia", "mecanismo"), { wrapper: wrapper(newClient()) });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/loops", { suite: "mecanismo" });
    expect(result.current.data?.[0].id).toBe("l1");
  });

  it("polls while a round is executando and stops once it settles", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockGet.mockResolvedValueOnce({ items: [loop({ serie: [{ rodada: 1, run_id: "r1", status: "executando", score: null, custo_usd: 0, compiled_hash: "h", melhorou: null, overcall: false, falhas: [] }] })] });
      mockGet.mockResolvedValue({ items: [loop({ rodadas_feitas: 1, serie: [{ rodada: 1, run_id: "r1", status: "concluida", score: 0.6, custo_usd: 1, compiled_hash: "h", melhorou: null, overcall: false, falhas: [] }] })] });
      const { useEvalLoops } = await import("@/hooks/studio/useEvalLoops");
      const { result } = renderHook(() => useEvalLoops("isaia"), { wrapper: wrapper(newClient()) });
      await waitFor(() => expect(result.current.data).toBeDefined());
      await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
      await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
      await act(async () => { await vi.advanceTimersByTimeAsync(7000); });
      expect(mockGet).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("useEvalLoop", () => {
  it("GETs one loop", async () => {
    mockGet.mockResolvedValue(loop());
    const { useEvalLoop } = await import("@/hooks/studio/useEvalLoops");
    const { result } = renderHook(() => useEvalLoop("isaia", "l1"), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(result.current.data?.id).toBe("l1"));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/loops/l1");
  });
});

describe("useCreateEvalLoop", () => {
  it("POSTs and writes the server's loop into the lists + detail while the refetch is still pending", async () => {
    mockGet.mockResolvedValueOnce({ items: [] });
    const { useEvalLoops, useCreateEvalLoop, loopsKey } = await import("@/hooks/studio/useEvalLoops");
    const qc = newClient();
    const { result: list } = renderHook(() => useEvalLoops("isaia", "comportamento"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.current.data).toEqual([]));
    mockPost.mockResolvedValue(loop());
    mockGet.mockReturnValue(new Promise(() => {})); // the settle refetch never answers: the write must already be in the cache
    const { result } = renderHook(() => useCreateEvalLoop("isaia"), { wrapper: wrapper(qc) });
    await act(async () => { await result.current.mutateAsync({ suite: "comportamento", rodadas_planejadas: 30 }); });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/loops", { suite: "comportamento", rodadas_planejadas: 30 });
    await waitFor(() => expect(list.current.data?.map((l) => l.id)).toEqual(["l1"]));
    expect(qc.getQueryData([...loopsKey("isaia"), "detail", "l1"])).toMatchObject({ id: "l1" });
  });

  it("does not put a loop into another suite's list", async () => {
    mockGet.mockResolvedValueOnce({ items: [] });
    const { useEvalLoops, useCreateEvalLoop } = await import("@/hooks/studio/useEvalLoops");
    const qc = newClient();
    const { result: list } = renderHook(() => useEvalLoops("isaia", "mecanismo"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.current.data).toEqual([]));
    mockPost.mockResolvedValue(loop());
    mockGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCreateEvalLoop("isaia"), { wrapper: wrapper(qc) });
    await act(async () => { await result.current.mutateAsync({ suite: "comportamento", rodadas_planejadas: 5, orcamento_usd: 3 }); });
    expect(list.current.data).toEqual([]);
  });
});

describe("useStopEvalLoop", () => {
  it("POSTs stop and replaces the loop in place", async () => {
    mockGet.mockResolvedValueOnce({ items: [loop()] });
    const { useEvalLoops, useStopEvalLoop } = await import("@/hooks/studio/useEvalLoops");
    const qc = newClient();
    const { result: list } = renderHook(() => useEvalLoops("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.current.data?.length).toBe(1));
    mockPost.mockResolvedValue(loop({ status: "parado", motivo_parada: "parado_manualmente" }));
    mockGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useStopEvalLoop("isaia"), { wrapper: wrapper(qc) });
    await act(async () => { await result.current.mutateAsync({ loopId: "l1" }); });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/loops/l1/stop", {});
    await waitFor(() => expect(list.current.data?.[0].status).toBe("parado"));
  });
});

describe("useRunLoopRound", () => {
  it("behaviour: POSTs the run with loop_id", async () => {
    mockPost.mockResolvedValue({ id: "r1" });
    mockGet.mockResolvedValue({ items: [] });
    const { useRunLoopRound } = await import("@/hooks/studio/useEvalLoops");
    const { result } = renderHook(() => useRunLoopRound("isaia", "comportamento"), { wrapper: wrapper(newClient()) });
    await act(async () => { await result.current.mutateAsync({ loopId: "l1", versionId: "v1" }); });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/runs", { version_id: "v1", loop_id: "l1" });
  });

  it("mechanism: POSTs the mechanism run with ?loop_id=", async () => {
    mockPost.mockResolvedValue({ run_id: "m1" });
    mockGet.mockResolvedValue({ items: [] });
    const { useRunLoopRound } = await import("@/hooks/studio/useEvalLoops");
    const { result } = renderHook(() => useRunLoopRound("isaia", "mecanismo"), { wrapper: wrapper(newClient()) });
    await act(async () => { await result.current.mutateAsync({ loopId: "l1", versionId: "" }); });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/draft/mecanismo-runs?loop_id=l1");
  });
});

describe("loop config", () => {
  it("GETs the config and PUT writes the server answer into the cache while the refetch is pending", async () => {
    mockGet.mockResolvedValueOnce({ alvo: 0.95, orcamento_usd: 5, rodadas_max: 10, alterado_por: null, alterado_em: null });
    const { useLoopConfig, useUpdateLoopConfig, loopConfigKey, LOOP_CONFIG_PATH } = await import("@/hooks/studio/useEvalLoops");
    const qc = newClient();
    const { result: cfg } = renderHook(() => useLoopConfig(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(cfg.current.data?.rodadas_max).toBe(10));
    expect(mockGet).toHaveBeenCalledWith(LOOP_CONFIG_PATH);
    const put = vi.fn().mockResolvedValue({ alvo: 0.9, orcamento_usd: 4, rodadas_max: 6, alterado_por: "u1", alterado_em: "2026-11-12T00:00:00Z" });
    const { api } = await import("@/lib/api");
    (api as unknown as { put: unknown }).put = put;
    mockGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useUpdateLoopConfig(), { wrapper: wrapper(qc) });
    await act(async () => { await result.current.mutateAsync({ alvo: 0.9, orcamento_usd: 4, rodadas_max: 6 }); });
    expect(put).toHaveBeenCalledWith(LOOP_CONFIG_PATH, { alvo: 0.9, orcamento_usd: 4, rodadas_max: 6 });
    expect(qc.getQueryData(loopConfigKey)).toMatchObject({ rodadas_max: 6 });
  });
});
