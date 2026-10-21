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

  it("a new decision is the last row of 'todas' and of its own estado, and absent from other estados", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["decisoes", "list", "todas"], { items: [{ codigo: "D-01", estado: "vigente" }], total: 1 });
    qc.setQueryData(["decisoes", "list", "vigente"], { items: [{ codigo: "D-01", estado: "vigente" }], total: 1 });
    qc.setQueryData(["decisoes", "list", "superseded"], { items: [], total: 0 });
    mockPost.mockResolvedValue({ codigo: "D-02", estado: "vigente" });
    const { useCreateDecisao } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useCreateDecisao(), { wrapper: w });
    result.current.mutate({ titulo: "t", decisao: "d", motivo: "m" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const codes = (k: string) => qc.getQueryData<any>(["decisoes", "list", k]).items.map((x: any) => x.codigo);
    expect(codes("todas")).toEqual(["D-01", "D-02"]);
    expect(codes("vigente")).toEqual(["D-01", "D-02"]);
    expect(qc.getQueryData<any>(["decisoes", "list", "vigente"]).total).toBe(2);
    expect(codes("superseded")).toEqual([]);
  });

  it("a new question joins 'aberta' and 'todas' but not 'respondida'", async () => {
    const { qc, w } = setup();
    for (const e of ["aberta", "respondida", "todas"]) qc.setQueryData(["perguntas", "list", e], { items: [], total: 0 });
    mockPost.mockResolvedValue({ codigo: "Q-01", estado: "aberta" });
    const { useCreatePergunta } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => useCreatePergunta(), { wrapper: w });
    result.current.mutate({ pergunta: "p", por_que_importa: "x", bloqueia: "y" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const n = (e: string) => qc.getQueryData<any>(["perguntas", "list", e]).items.length;
    expect([n("aberta"), n("todas"), n("respondida")]).toEqual([1, 1, 0]);
  });

  it("a new task joins only the task lists whose fase/estado filter it satisfies", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["roadmap", "tasks", {}], { items: [], total: 0 });
    qc.setQueryData(["roadmap", "tasks", { fase: "F1" }], { items: [], total: 0 });
    qc.setQueryData(["roadmap", "tasks", { fase: "F2" }], { items: [], total: 0 });
    qc.setQueryData(["roadmap", "tasks", { estado: "concluida" }], { items: [], total: 0 });
    mockPost.mockResolvedValue({ codigo: "T-001", fase: "F1", estado: "pendente" });
    const { useCreateTask } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => useCreateTask(), { wrapper: w });
    result.current.mutate({ titulo: "t", fase: "F1" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const n = (p: object) => qc.getQueryData<any>(["roadmap", "tasks", p]).items.length;
    expect([n({}), n({ fase: "F1" }), n({ fase: "F2" }), n({ estado: "concluida" })]).toEqual([1, 1, 0, 0]);
  });
});
