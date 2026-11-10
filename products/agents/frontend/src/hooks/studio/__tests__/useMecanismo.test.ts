/** useMecanismo — the queued-job handoff: POST seeds the run, GET polls while executando, a terminal poll refetches prontidão once. */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

import { useIniciarMecanismo, useMecanismoRun } from "@/hooks/studio/useMecanismo";
import { studioKeys } from "@/hooks/studio/keys";

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const wrapper = (qc: QueryClient) => ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: qc }, children);

beforeEach(() => vi.clearAllMocks());

const RUN = { run_id: "r1", version_id: "v1", compiled_hash: "h", driver: "live", aprovado: true, completo: true, orcamento_excedido: false, custo_usd: 0.1, total_casos: 2, casos_aprovados: 2, erro: null, casos: [] };

describe("useIniciarMecanismo", () => {
  it("POSTs to the draft route and seeds the run as executando", async () => {
    mockPost.mockResolvedValue({ run_id: "r1", compiled_hash: "h", driver: "live", status: "executando" });
    const qc = newClient();
    const { result } = renderHook(() => useIniciarMecanismo("julia"), { wrapper: wrapper(qc) });
    await act(async () => { await result.current.mutateAsync(); });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/julia/draft/mecanismo-runs");
    expect(qc.getQueryData<{ status: string }>(["studio", "julia", "mecanismo-run", "r1"])?.status).toBe("executando");
  });
});

describe("useMecanismoRun", () => {
  it("does not fetch without a run id", () => {
    renderHook(() => useMecanismoRun("julia", null), { wrapper: wrapper(newClient()) });
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("refetches prontidão and detail when the run settles", async () => {
    mockGet.mockResolvedValue({ ...RUN, status: "concluida" });
    const qc = newClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useMecanismoRun("julia", "r1"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.data?.status).toBe("concluida"));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/julia/mecanismo-runs/r1");
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: studioKeys.prontidao("julia") }));
    expect(spy).toHaveBeenCalledWith({ queryKey: studioKeys.detail("julia") });
  });

  it("does not refetch prontidão while still executando", async () => {
    mockGet.mockResolvedValue({ ...RUN, status: "executando" });
    const qc = newClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useMecanismoRun("julia", "r1"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.data?.status).toBe("executando"));
    expect(spy).not.toHaveBeenCalledWith({ queryKey: studioKeys.prontidao("julia") });
  });
});

describe("useMecanismoRun request budget", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stops polling when the run read fails (a 404 must not poll every 3 s forever)", async () => {
    mockGet.mockRejectedValue(new Error("404"));
    const { result } = renderHook(() => useMecanismoRun("julia", "r1"), { wrapper: wrapper(newClient()) });
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(result.current.isError).toBe(true);
    const before = mockGet.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(mockGet.mock.calls.length).toBe(before);
  });
});
