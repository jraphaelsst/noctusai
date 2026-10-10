/** Esteira hooks hit the contract §5 endpoints, share cache keys and invalidate the right families. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import {
  esteiraKeys,
  useAtualizarPost,
  useCriarMembro,
  useCriarPost,
  useDesvincularHeadline,
  useDesvincularRoteiro,
  useEquipe,
  useEsteiraBoard,
  useExcluirPost,
  useGerarLegenda,
  usePost,
  useVincularHeadline,
  useVincularRoteiro,
} from "./useEsteira";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

afterEach(() => {
  vi.restoreAllMocks();
  qc.clear();
  Object.values(api).forEach((m) => m.mockReset());
});

const FAMILIES = [
  { queryKey: ["sw-esteira"] },
  { queryKey: ["sw", "esteira"] },
  { queryKey: ["sw", "geracao"] },
];

describe("useEsteiraBoard", () => {
  it("lê /board, cacheia o array de colunas sob a chave do pipeline e expõe orfaos", async () => {
    const colunas = [{ etapa: "e1", stage: {}, cards: [], total: 0, exibidos: 0 }];
    api.get.mockResolvedValue({ data: { colunas, orfaos: 2 } });
    const { result } = renderHook(() => useEsteiraBoard({ marca_id: "m1", busca: "" }), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.colunas).toEqual(colunas));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/esteira/board?marca_id=m1");
    expect(qc.getQueryData(["sw-esteira", { marca_id: "m1" }])).toEqual(colunas);
    await waitFor(() => expect(result.current.orfaos).toBe(2));
    expect(result.current.showSkeleton).toBe(false);
  });

  it("filtros vazios compartilham a mesma chave", () => {
    expect(esteiraKeys.board({})).toEqual(["sw-esteira", {}]);
  });
});

describe("usePost", () => {
  it("fica desabilitado sem id e consulta /posts/{id}", async () => {
    const off = renderHook(() => usePost(null), { wrapper });
    expect(off.result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
    api.get.mockResolvedValue({ data: { id: "p1", lote_ativo: null } });
    const { result } = renderHook(() => usePost("p1"), { wrapper });
    await waitFor(() => expect(result.current.data?.id).toBe("p1"));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1");
  });
});

describe("post mutations", () => {
  it("criar -> POST /posts e invalida board, esteira e geracao", async () => {
    api.post.mockResolvedValue({ data: { id: "p1" } });
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCriarPost(), { wrapper });
    await result.current.mutateAsync({ marca_id: "m1", titulo: "t" });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/esteira/posts", { marca_id: "m1", titulo: "t" });
    await waitFor(() => FAMILIES.forEach((f) => expect(inv).toHaveBeenCalledWith(f)));
  });

  it("atualizar -> PATCH /posts/{id} com o patch", async () => {
    api.patch.mockResolvedValue({ data: { id: "p1" } });
    const { result } = renderHook(() => useAtualizarPost(), { wrapper });
    await result.current.mutateAsync({ id: "p1", patch: { legenda: "x", conta_id: null } });
    expect(api.patch).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1", { legenda: "x", conta_id: null });
  });

  it("excluir -> DELETE /posts/{id}", async () => {
    api.delete.mockResolvedValue(undefined);
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useExcluirPost(), { wrapper });
    await result.current.mutateAsync("p1");
    expect(api.delete).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1");
    await waitFor(() => FAMILIES.forEach((f) => expect(inv).toHaveBeenCalledWith(f)));
  });
});

describe("bind / unbind", () => {
  it("headline: PUT {headline_id} ou {texto}; DELETE desvincula", async () => {
    api.put.mockResolvedValue({ data: { id: "p1" } });
    api.delete.mockResolvedValue(undefined);
    const bind = renderHook(() => useVincularHeadline(), { wrapper });
    await bind.result.current.mutateAsync({ postId: "p1", body: { headline_id: "h1" } });
    await bind.result.current.mutateAsync({ postId: "p1", body: { texto: "novo" } });
    expect(api.put.mock.calls).toEqual([
      ["/api/media-creation/esteira/posts/p1/headline", { headline_id: "h1" }],
      ["/api/media-creation/esteira/posts/p1/headline", { texto: "novo" }],
    ]);
    const un = renderHook(() => useDesvincularHeadline(), { wrapper });
    await un.result.current.mutateAsync("p1");
    expect(api.delete).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1/headline");
  });

  it("roteiro: PUT {roteiro_id}; DELETE desvincula", async () => {
    api.put.mockResolvedValue({ data: { id: "p1" } });
    api.delete.mockResolvedValue(undefined);
    const bind = renderHook(() => useVincularRoteiro(), { wrapper });
    await bind.result.current.mutateAsync({ postId: "p1", roteiroId: "r1" });
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1/roteiro", { roteiro_id: "r1" });
    const un = renderHook(() => useDesvincularRoteiro(), { wrapper });
    await un.result.current.mutateAsync("p1");
    expect(api.delete).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1/roteiro");
  });
});

describe("legenda", () => {
  it("gera via POST e NÃO invalida nada (resultado não é salvo)", async () => {
    api.post.mockResolvedValue({ data: { legenda: "l", hashtags: ["#a"], primeiro_comentario: "c" } });
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useGerarLegenda(), { wrapper });
    const r = await result.current.mutateAsync("p1");
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1/legenda/gerar");
    expect(r.hashtags).toEqual(["#a"]);
    expect(inv).not.toHaveBeenCalled();
  });
});

describe("equipe", () => {
  it("lista com e sem inativos em chaves distintas", async () => {
    api.get.mockResolvedValue({ data: [] });
    const a = renderHook(() => useEquipe(), { wrapper });
    await waitFor(() => expect(a.result.current.data).toEqual([]));
    const b = renderHook(() => useEquipe(true), { wrapper });
    await waitFor(() => expect(b.result.current.data).toEqual([]));
    expect(api.get.mock.calls.map((c) => c[0])).toEqual([
      "/api/media-creation/equipe",
      "/api/media-creation/equipe?incluir_inativos=true",
    ]);
    expect(esteiraKeys.equipe(false)).not.toEqual(esteiraKeys.equipe(true));
  });

  it("criar membro invalida o board (cards mostram membros)", async () => {
    api.post.mockResolvedValue({ data: { id: "mb1" } });
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCriarMembro(), { wrapper });
    await result.current.mutateAsync({ nome: "Ana" });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/equipe", { nome: "Ana" });
    await waitFor(() => expect(inv).toHaveBeenCalledWith({ queryKey: ["sw-esteira"] }));
  });
});
