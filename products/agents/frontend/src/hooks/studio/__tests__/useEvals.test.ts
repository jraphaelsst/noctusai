/**
 * useEvals.ts hook tests — Agent Studio CONTRACT.md §D4. Covers cases CRUD
 * request shapes, run creation/listing, and the "poll while in-flight,
 * stop once settled" `refetchInterval` rule
 * (mirrors `products/erp-imobiliario/frontend/src/hooks/useCertidoes.ts`).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

beforeEach(() => vi.clearAllMocks());

const CASE = {
  id: "e1",
  slug: "pergunta-reels",
  titulo: "Pergunta sobre reels",
  entrada: "Como faço um reels?",
  contexto: null,
  criterios: { deve: ["menciona roteiro"], nao_deve: [] },
  rubrica: null,
  tags: [],
  ativo: true,
};

describe("useEvalCases", () => {
  it("GETs the agent's eval cases", async () => {
    mockGet.mockResolvedValue({ items: [CASE] });
    const { useEvalCases } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    const { result } = renderHook(() => useEvalCases("isaia"), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/cases");
    expect(result.current.data?.[0].slug).toBe("pergunta-reels");
  });
});

describe("useCreateEvalCase", () => {
  it("POSTs the case payload verbatim (contract field names)", async () => {
    mockGet.mockResolvedValue({ items: [] });
    mockPost.mockResolvedValue(CASE);
    const { useEvalCases, useCreateEvalCase } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    const list = renderHook(() => useEvalCases("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.result.current.showSkeleton).toBe(false));

    const create = renderHook(() => useCreateEvalCase("isaia"), { wrapper: wrapper(qc) });
    const { id, ...payload } = CASE;
    void id;
    await create.result.current.mutateAsync(payload);

    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/cases", payload);
  });
});

describe("useCreateEvalRun", () => {
  it("POSTs {version_id, case_ids?} and seeds the run-detail cache", async () => {
    mockPost.mockResolvedValue({ id: "r1", version_id: "v1", compiled_hash: "sha256:aaaa", status: "pendente", total: 0, aprovados: 0, score: null, limiar: 0.8, started_by: "u1", started_at: null, finished_at: null, erro: null });
    const { useCreateEvalRun } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    const { result } = renderHook(() => useCreateEvalRun("isaia"), { wrapper: wrapper(qc) });

    const run = await result.current.mutateAsync({ version_id: "v1" });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/evals/runs", { version_id: "v1" });
    expect(run.status).toBe("pendente");
  });
});

describe("studioKeys.detail invalidation (score-affecting events)", () => {
  it("useCreateEvalRun invalidates the agent detail query", async () => {
    mockPost.mockResolvedValue({ id: "r1", version_id: "v1", compiled_hash: "sha256:aaaa", status: "pendente", total: 0, aprovados: 0, score: null, limiar: 0.8, started_by: "u1", started_at: null, finished_at: null, erro: null });
    const { useCreateEvalRun } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    qc.setQueryData(["studio", "isaia", "detail"], { key: "isaia" });
    const { result } = renderHook(() => useCreateEvalRun("isaia"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ version_id: "v1" });

    const detailQuery = qc.getQueryCache().find({ queryKey: ["studio", "isaia", "detail"] });
    expect(detailQuery?.state.isInvalidated).toBe(true);
  });

  it("useCancelEvalRun invalidates the agent detail query", async () => {
    mockPost.mockResolvedValue({ id: "r1", version_id: "v1", compiled_hash: "sha256:aaaa", status: "cancelada", total: 0, aprovados: 0, score: null, limiar: 0.8, started_by: "u1", started_at: null, finished_at: null, erro: null });
    const { useCancelEvalRun } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    qc.setQueryData(["studio", "isaia", "detail"], { key: "isaia" });
    const { result } = renderHook(() => useCancelEvalRun("isaia"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync("r1");

    const detailQuery = qc.getQueryCache().find({ queryKey: ["studio", "isaia", "detail"] });
    expect(detailQuery?.state.isInvalidated).toBe(true);
  });

  it("useEvalRun invalidates the agent detail query the moment a poll observes a terminal status", async () => {
    mockGet.mockResolvedValueOnce({
      id: "r1", version_id: "v1", compiled_hash: "h", status: "executando", total: 1, aprovados: 0, score: null, limiar: 0.8, started_at: "t", finished_at: null, erro: null, resultados: [],
    });
    const { useEvalRun } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    qc.setQueryData(["studio", "isaia", "detail"], { key: "isaia" });
    const { result } = renderHook(() => useEvalRun("isaia", "r1"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.data?.status).toBe("executando"));

    // Still in flight — no premature invalidation.
    let detailQuery = qc.getQueryCache().find({ queryKey: ["studio", "isaia", "detail"] });
    expect(detailQuery?.state.isInvalidated).toBe(false);

    mockGet.mockResolvedValueOnce({
      id: "r1", version_id: "v1", compiled_hash: "h", status: "concluida", total: 1, aprovados: 1, score: 0.95, limiar: 0.8, started_at: "t", finished_at: "t2", erro: null, resultados: [],
    });
    await qc.invalidateQueries({ queryKey: ["studio", "isaia", "evals", "runs", "detail", "r1"] });
    await waitFor(() => expect(result.current.data?.status).toBe("concluida"));

    await waitFor(() => {
      detailQuery = qc.getQueryCache().find({ queryKey: ["studio", "isaia", "detail"] });
      expect(detailQuery?.state.isInvalidated).toBe(true);
    });
  });
});

describe("useEvalRuns polling", () => {
  it("polls every 3s while a run is executando", async () => {
    mockGet.mockResolvedValue({
      items: [{ id: "r1", version_id: "v1", compiled_hash: "h", status: "executando", total: 2, aprovados: 0, score: null, limiar: 0.8, started_at: "t", finished_at: null, erro: null }],
    });
    const { useEvalRuns } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    const { result } = renderHook(() => useEvalRuns("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));

    const query = qc.getQueryCache().find({ queryKey: ["studio", "isaia", "evals", "runs", null] });
    const refetchInterval = (query as any).options.refetchInterval;
    expect(refetchInterval(query)).toBe(3000);
  });

  it("stops polling once every run has settled", async () => {
    mockGet.mockResolvedValue({
      items: [{ id: "r1", version_id: "v1", compiled_hash: "h", status: "concluida", total: 2, aprovados: 2, score: 0.9, limiar: 0.8, started_at: "t", finished_at: "t2", erro: null }],
    });
    const { useEvalRuns } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    const { result } = renderHook(() => useEvalRuns("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));

    const query = qc.getQueryCache().find({ queryKey: ["studio", "isaia", "evals", "runs", null] });
    const refetchInterval = (query as any).options.refetchInterval;
    expect(refetchInterval(query)).toBe(false);
  });
});

describe("consolidation counters refresh when a run finishes (no run-detail panel open)", () => {
  const RUN = { id: "r1", version_id: "v1", compiled_hash: "h", total: 2, aprovados: 0, score: null, limiar: 0.8, started_at: "t", finished_at: null, erro: null };

  it("the runs-list poll invalidates consolidacao and detail on the in-flight -> terminal transition", async () => {
    mockGet.mockResolvedValueOnce({ items: [{ ...RUN, status: "executando" }] });
    const { useEvalRuns } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    for (const k of [["studio", "isaia", "evals", "consolidacao"], ["studio", "isaia", "detail"]]) qc.setQueryData(k, {});
    const { result } = renderHook(() => useEvalRuns("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.data?.[0].status).toBe("executando"));
    const consolidacao = () => qc.getQueryCache().find({ queryKey: ["studio", "isaia", "evals", "consolidacao"] });
    expect(consolidacao()?.state.isInvalidated).toBe(false);

    mockGet.mockResolvedValueOnce({ items: [{ ...RUN, status: "concluida", aprovados: 2, score: 1, finished_at: "t2" }] });
    await qc.invalidateQueries({ queryKey: ["studio", "isaia", "evals", "runs", null] });
    await waitFor(() => expect(result.current.data?.[0].status).toBe("concluida"));

    await waitFor(() => expect(consolidacao()?.state.isInvalidated).toBe(true));
    expect(qc.getQueryCache().find({ queryKey: ["studio", "isaia", "detail"] })?.state.isInvalidated).toBe(true);
  });

  it("a run already terminal on first load is old news: nothing is invalidated", async () => {
    mockGet.mockResolvedValueOnce({ items: [{ ...RUN, status: "concluida", finished_at: "t2" }] });
    const { useEvalRuns } = await import("@/hooks/studio/useEvals");
    const qc = newClient();
    qc.setQueryData(["studio", "isaia", "evals", "consolidacao"], {});
    const { result } = renderHook(() => useEvalRuns("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(qc.getQueryCache().find({ queryKey: ["studio", "isaia", "evals", "consolidacao"] })?.state.isInvalidated).toBe(false);
  });

  it("runsThatFinished only names runs seen in flight before", async () => {
    const { runsThatFinished } = await import("@/hooks/studio/useEvals");
    expect(runsThatFinished(new Set(["a", "b"]), [
      { id: "a", status: "concluida" }, { id: "b", status: "executando" }, { id: "c", status: "falhou" },
    ])).toEqual(["a"]);
  });
});
