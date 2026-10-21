/**
 * Cache writes (wave 2 of the invalidate-only fan-out): the hooks put what they know into
 * the cache while the request is in flight / the moment it answers.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete },
}));

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const w = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
}

beforeEach(() => {
  vi.resetAllMocks();
  mockGet.mockReturnValue(new Promise(() => {})); // the settle refetch must never be what the test relies on
});

describe("academia cache writes", () => {
  it("a deleted interessado leaves its page on the click and the total follows", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["interessados", "list", 50, 0], { items: [{ id: "i1" }, { id: "i2" }], total: 2 });
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { useDeleteInteressado } = await import("@/hooks/useInteressados");
    const { result } = renderHook(() => useDeleteInteressado(), { wrapper: w });
    result.current.mutate("i1");
    await waitFor(() =>
      expect(qc.getQueryData(["interessados", "list", 50, 0])).toEqual({ items: [{ id: "i2" }], total: 1 }),
    );
  });

  it("superseding a decision rewrites the old one in the list and seeds the new one's detail", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["decisoes", "list", "todas"], { items: [{ codigo: "D-1", estado: "vigente" }], total: 1 });
    mockPost.mockResolvedValue({
      nova: { codigo: "D-2", estado: "vigente" },
      substituida: { codigo: "D-1", estado: "superseded" },
    });
    const { useSupersedeDecisao } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useSupersedeDecisao("D-1"), { wrapper: w });
    result.current.mutate({ titulo: "t", decisao: "d", motivo: "m" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any>(["decisoes", "list", "todas"]).items[0].estado).toBe("superseded");
    expect(qc.getQueryData<any>(["decisoes", "detail", "D-2"]).codigo).toBe("D-2");
  });

  it("an edited KB entry is the server's row in the list and the detail", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["kb", "list", {}], { items: [{ slug: "a", titulo: "Velho" }], total: 1 });
    mockPut.mockResolvedValue({ slug: "a", titulo: "Novo" });
    const { useUpdateKb } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useUpdateKb("a"), { wrapper: w });
    result.current.mutate({ titulo: "Novo", motivo: "x" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any>(["kb", "list", {}]).items[0].titulo).toBe("Novo");
    expect(qc.getQueryData<any>(["kb", "detail", "a"]).titulo).toBe("Novo");
  });

  it("an answered question leaves the open list", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["perguntas", "list", "aberta"], { items: [{ codigo: "Q-1" }], total: 1 });
    mockPost.mockResolvedValue({ codigo: "Q-1", estado: "respondida" });
    const { useAnswerPergunta } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => useAnswerPergunta("Q-1"), { wrapper: w });
    result.current.mutate("sim");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(["perguntas", "list", "aberta"])).toEqual({ items: [], total: 0 });
  });

  it("a task edit is drawn on the click in every cached list and rolled back on failure", async () => {
    const { qc, w } = setup();
    const key = ["roadmap", "tasks", { fase: "F1" }];
    qc.setQueryData(key, { items: [{ codigo: "T-1", estado: "pendente" }], total: 1 });
    mockPatch.mockRejectedValue(new Error("boom"));
    const { useUpdateTask } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => useUpdateTask(), { wrapper: w });
    result.current.mutate({ codigo: "T-1", changes: { estado: "concluida" } });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData<any>(key).items[0].estado).toBe("pendente");
  });
});
