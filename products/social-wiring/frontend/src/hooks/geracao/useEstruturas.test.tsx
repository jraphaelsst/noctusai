/**
 * useEstruturas hits the §6 endpoints with the contract's params/bodies and writes every answer into the
 * caches it touches (detail + cached list rows) — fixtures are typed from §11.1; the network edge is mocked.
 */
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { bloco, detalheAdmin, importacao, resumo, TIPOS } from "@/test/estruturasFixtures";
import {
  estruturaKey,
  estruturasQuery,
  useAdicionarVideoPorLink,
  useArquivarEstrutura,
  useAtualizarEstrutura,
  useConfirmarEstrutura,
  useEstruturaDetalhe,
  useEstruturas,
  useEstruturasAdmin,
  useExcluirEstrutura,
  useImportacoes,
  usePublicarEstrutura,
  useSalvarTipoBloco,
  useSubstituirBlocos,
  useTiposBloco,
} from "./useEstruturas";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;

afterEach(() => {
  qc.clear();
  Object.values(api).forEach((f) => f.mockReset());
});

const LISTA = ["sw", "geracao", "estruturas", "lista"] as const;

describe("reads", () => {
  it("serialises every filter the contract names, repeating formato/objetivo", () => {
    const url = new URL(
      `http://x/?${estruturasQuery({
        marcaId: "m1",
        perfilId: "p1",
        q: "  autoridade  ",
        formatos: ["reels", "post"],
        objetivos: ["venda"],
        status: "rascunho",
        somentePendentesRevisao: true,
        limit: 50,
        offset: 100,
      })}`,
    );
    expect(url.searchParams.get("marca_id")).toBe("m1");
    expect(url.searchParams.get("perfil_id")).toBe("p1");
    expect(url.searchParams.get("q")).toBe("autoridade");
    expect(url.searchParams.getAll("formato")).toEqual(["reels", "post"]);
    expect(url.searchParams.getAll("objetivo")).toEqual(["venda"]);
    expect(url.searchParams.get("status")).toBe("rascunho");
    expect(url.searchParams.get("somente_pendentes_revisao")).toBe("true");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("offset")).toBe("100");
  });

  it("useEstruturas: skeleton only before the first data; `{items,total}` page", async () => {
    api.get.mockResolvedValue({ data: { items: [resumo()], total: 1 } });
    const { result } = renderHook(() => useEstruturas({ perfilId: "p1" }), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.total).toBe(1));
    expect(result.current.showSkeleton).toBe(false);
    expect(new URL(api.get.mock.calls[0][0], "http://x").pathname).toBe("/api/media-creation/estruturas");
  });

  it("does not fetch while disabled, and the detail only with an id", () => {
    renderHook(() => useEstruturas({}, false), { wrapper });
    renderHook(() => useEstruturaDetalhe(null), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
  });

  it("admin flag, detail and catalog hit their routes", async () => {
    api.get.mockImplementation(async (url: string) => {
      if (url.endsWith("/estruturas/admin")) return { data: { is_admin: true } };
      if (url.endsWith("/estruturas/tipos-bloco")) return { data: TIPOS };
      return { data: detalheAdmin() };
    });
    const a = renderHook(() => useEstruturasAdmin(), { wrapper });
    const t = renderHook(() => useTiposBloco(), { wrapper });
    const d = renderHook(() => useEstruturaDetalhe("e1"), { wrapper });
    await waitFor(() => expect(a.result.current.data).toBe(true));
    await waitFor(() => expect(t.result.current.data).toHaveLength(5));
    await waitFor(() => expect(d.result.current.data?.versao).toBe(3));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/estruturas/e1");
  });

  it("importações: pages the report", async () => {
    api.get.mockResolvedValue({ data: { items: [importacao()], total: 1 } });
    const { result } = renderHook(() => useImportacoes(20, 40), { wrapper });
    await waitFor(() => expect(result.current.data?.items[0]?.id).toBe("i1"));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/estruturas/importacoes?limit=20&offset=40");
  });
});

describe("writes fill every cache entry they touch (§11.4)", () => {
  function semear(admin = detalheAdmin()) {
    qc.setQueryData(estruturaKey("e1"), admin);
    qc.setQueryData([...LISTA, { perfilId: "p1" }], { items: [resumo({ pendente_revisao: true }), resumo({ id: "e2", codigo: 102 })], total: 2 });
    qc.setQueryData([...LISTA, { somentePendentesRevisao: true }], { items: [resumo({ pendente_revisao: true })], total: 1 });
  }

  it("confirmar: sends exactly one of campos | todos, writes the detail and flips the list row's pendente_revisao", async () => {
    semear();
    const confirmado = detalheAdmin({
      versao: 4,
      pendente_revisao: false,
      proveniencia: { formula_headline: "admin", formato: "fonte", objetivos: "admin" },
      blocos: [bloco({ proveniencia: { nome: "fonte", tipo: "admin", tempo: "fonte", instrucao: "admin" } })],
    });
    api.post.mockResolvedValue({ data: confirmado });
    const { result } = renderHook(() => useConfirmarEstrutura(), { wrapper });
    await act(() => result.current.mutateAsync({ id: "e1", expected_versao: 3, todos: true }));
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/estruturas/e1/confirmar", { expected_versao: 3, todos: true });
    expect(qc.getQueryData<typeof confirmado>(estruturaKey("e1"))?.versao).toBe(4);
    const lista = qc.getQueryData<{ items: { id: string; pendente_revisao?: boolean }[] }>([...LISTA, { perfilId: "p1" }]);
    expect(lista?.items[0]?.pendente_revisao).toBe(false);
    expect(lista?.items[1]?.id).toBe("e2");
    // The list row never grows the detail-only fields.
    expect(lista?.items[0]).not.toHaveProperty("blocos");
    expect(lista?.items[0]).not.toHaveProperty("versao");
  });

  it("atualizar + substituir blocos send the contract bodies (expected_versao, no id in the URL body)", async () => {
    semear();
    api.patch.mockResolvedValue({ data: detalheAdmin({ versao: 4, formula_headline: "Nova" }) });
    api.put.mockResolvedValue({ data: detalheAdmin({ versao: 5 }) });
    const up = renderHook(() => useAtualizarEstrutura(), { wrapper });
    const bl = renderHook(() => useSubstituirBlocos(), { wrapper });
    await act(() => up.result.current.mutateAsync({ id: "e1", expected_versao: 3, formula_headline: "Nova" }));
    expect(api.patch).toHaveBeenCalledWith("/api/media-creation/estruturas/e1", { expected_versao: 3, formula_headline: "Nova" });
    await act(() => bl.result.current.mutateAsync({ id: "e1", expected_versao: 4, blocos: [{ id: "b1", nome: "A", tipo_id: "t1" }] }));
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/estruturas/e1/blocos", { expected_versao: 4, blocos: [{ id: "b1", nome: "A", tipo_id: "t1" }] });
    expect(qc.getQueryData<{ versao: number }>(estruturaKey("e1"))?.versao).toBe(5);
  });

  it("publicar / arquivar / restaurar hit their routes", async () => {
    semear();
    api.post.mockResolvedValue({ data: detalheAdmin({ status: "ativa" }) });
    const pub = renderHook(() => usePublicarEstrutura(), { wrapper });
    const arq = renderHook(() => useArquivarEstrutura(), { wrapper });
    await act(() => pub.result.current.mutateAsync({ id: "e1", expected_versao: 3 }));
    await act(() => arq.result.current.mutateAsync({ id: "e1", acao: "arquivar" }));
    await act(() => arq.result.current.mutateAsync({ id: "e1", acao: "restaurar" }));
    expect(api.post.mock.calls.map((c) => c[0])).toEqual([
      "/api/media-creation/estruturas/e1/publicar",
      "/api/media-creation/estruturas/e1/arquivar",
      "/api/media-creation/estruturas/e1/restaurar",
    ]);
  });

  it("excluir drops the row from every cached list (and its total) and forgets the detail", async () => {
    semear();
    api.delete.mockResolvedValue(undefined);
    const { result } = renderHook(() => useExcluirEstrutura(), { wrapper });
    await act(() => result.current.mutateAsync("e1"));
    expect(api.delete).toHaveBeenCalledWith("/api/media-creation/estruturas/e1");
    const lista = qc.getQueryData<{ items: { id: string }[]; total: number }>([...LISTA, { perfilId: "p1" }]);
    expect(lista?.items.map((i) => i.id)).toEqual(["e2"]);
    expect(lista?.total).toBe(1);
    expect(qc.getQueryData(estruturaKey("e1"))).toBeUndefined();
  });

  it("a refused write rolls the optimistic delete back and surfaces the code", async () => {
    semear();
    api.delete.mockRejectedValue(Object.assign(new Error("[409] x"), { status: 409, code: "estrutura_em_uso" }));
    const { result } = renderHook(() => useExcluirEstrutura(), { wrapper });
    await expect(act(() => result.current.mutateAsync("e1"))).rejects.toMatchObject({ code: "estrutura_em_uso" });
    expect(qc.getQueryData<{ items: unknown[] }>([...LISTA, { perfilId: "p1" }])?.items).toHaveLength(2);
  });

  it("catalog: create posts, edit puts with expected_versao, both land sorted in the cached catalog", async () => {
    qc.setQueryData(["sw", "geracao", "estruturas", "tipos-bloco"], TIPOS);
    api.post.mockResolvedValue({ data: { id: "t5", nome: "Novo", ordem: 0, tempo_tipico: null, instrucao_referencia: "x", ativo: true } });
    api.put.mockResolvedValue({ data: { ...TIPOS[1]!, nome: "Revelação 2", versao: 2 } });
    const { result } = renderHook(() => useSalvarTipoBloco(), { wrapper });
    await act(() => result.current.mutateAsync({ nome: "Novo", instrucao_referencia: "x", ordem: 0 }));
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/estruturas/tipos-bloco", { nome: "Novo", instrucao_referencia: "x", ordem: 0 });
    await act(() => result.current.mutateAsync({ id: "t2", nome: "Revelação 2", instrucao_referencia: "x", expected_versao: 1 }));
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/estruturas/tipos-bloco/t2", { nome: "Revelação 2", instrucao_referencia: "x", expected_versao: 1 });
    const cat = qc.getQueryData<{ id: string; nome: string }[]>(["sw", "geracao", "estruturas", "tipos-bloco"]);
    expect(cat?.[0]?.id).toBe("t5");
    expect(cat?.find((t) => t.id === "t2")?.nome).toBe("Revelação 2");
  });

  it("por link: posts {url} and returns the outcome (200 ja_existia included)", async () => {
    api.post.mockResolvedValue({ data: { viral: { id: "v1" }, perfil_criado: false, ja_existia: true } });
    const { result } = renderHook(() => useAdicionarVideoPorLink(), { wrapper });
    const r = await act(() => result.current.mutateAsync("https://www.instagram.com/reel/AbC123/"));
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/biblioteca/virais/por-link", { url: "https://www.instagram.com/reel/AbC123/" });
    expect(r).toMatchObject({ ja_existia: true });
  });
});
