/** Headlines hooks hit the §4.4 endpoints; polling follows the REAL batch status. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import {
  algumLoteEmAndamento,
  useContagemEstruturas,
  useCriarLote,
  useExcluirLotes,
  useHeadline,
  useHeadlinesLista,
  useLote,
  useLotes,
  useReprocessarLote,
} from "./useHeadlines";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

afterEach(() => {
  qc.clear();
  api.get.mockReset();
  api.post.mockReset();
});

describe("algumLoteEmAndamento", () => {
  it("só criando/processando mantêm o polling", () => {
    expect(algumLoteEmAndamento([{ status: "completo" }, { status: "falha" }])).toBe(false);
    expect(algumLoteEmAndamento([{ status: "completo" }, { status: "processando" }])).toBe(true);
    expect(algumLoteEmAndamento([{ status: "criando" }])).toBe(true);
    expect(algumLoteEmAndamento(undefined)).toBe(false);
  });
});

describe("queries", () => {
  it("useLotes lista por marca e busca, sem usar isLoading", async () => {
    api.get.mockResolvedValue({ data: { items: [{ id: "l1", status: "completo" }], total: 1 } });
    const { result } = renderHook(() => useLotes("m1", " abc ", 20), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.total).toBe(1));
    expect(api.get).toHaveBeenCalledWith(
      "/api/media-creation/headlines/lotes?marca_id=m1&limit=20&offset=20&q=abc",
    );
    expect(result.current.showSkeleton).toBe(false);
  });

  it("useLotes não consulta sem marca", () => {
    renderHook(() => useLotes(null), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
  });

  it("useLote lê o detalhe do lote", async () => {
    api.get.mockResolvedValue({ data: { id: "l1", status: "completo", headlines: [] } });
    const { result } = renderHook(() => useLote("l1"), { wrapper });
    await waitFor(() => expect(result.current.data?.id).toBe("l1"));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/headlines/lotes/l1");
  });

  it("useHeadlinesLista envia lista e modo só nas sugeridas", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0 } });
    const a = renderHook(() => useHeadlinesLista("m1", "sugeridas", { modo: "automatico" }), { wrapper });
    await waitFor(() => expect(a.result.current.data).toBeTruthy());
    expect(api.get.mock.calls[0][0]).toContain("lista=sugeridas");
    expect(api.get.mock.calls[0][0]).toContain("modo=automatico");
    api.get.mockClear();
    const b = renderHook(() => useHeadlinesLista("m1", "favoritas", { modo: "manual" }), { wrapper });
    await waitFor(() => expect(b.result.current.data).toBeTruthy());
    expect(api.get.mock.calls[0][0]).toContain("lista=favoritas");
    expect(api.get.mock.calls[0][0]).not.toContain("modo=");
  });

  it("useHeadline busca a headline por id (?hid=)", async () => {
    api.get.mockResolvedValue({ data: { id: "h9" } });
    const { result } = renderHook(() => useHeadline("h9"), { wrapper });
    await waitFor(() => expect(result.current.data?.id).toBe("h9"));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/headlines/h9");
  });

  it("useContagemEstruturas repete variaveis[] e fica parado sem variáveis", async () => {
    api.get.mockResolvedValue({ data: { compativeis: 4, por_perfil: [] } });
    renderHook(() => useContagemEstruturas("m1", []), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
    const { result } = renderHook(() => useContagemEstruturas("m1", ["a", "b"]), { wrapper });
    await waitFor(() => expect(result.current.data?.compativeis).toBe(4));
    expect(api.get.mock.calls[0][0]).toContain("variaveis%5B%5D=a&variaveis%5B%5D=b");
  });
});

describe("mutations", () => {
  it("criar lote faz POST /lotes e invalida a família geracao", async () => {
    api.post.mockResolvedValue({ data: { id: "l1" } });
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCriarLote(), { wrapper });
    const body = { marca_id: "m1", origem: "form_viral" as const, assunto_livre: "x", criatividade: "equilibrado" as const };
    const lote = await result.current.mutateAsync(body);
    expect(lote.id).toBe("l1");
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/headlines/lotes", body);
    await waitFor(() => expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao"] }));
  });

  it("reprocessar e excluir usam as rotas do contrato", async () => {
    api.post.mockResolvedValue({ data: { id: "novo", excluidos: 2 } });
    const rep = renderHook(() => useReprocessarLote(), { wrapper });
    await rep.result.current.mutateAsync("l1");
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/headlines/lotes/l1/reprocessar");
    const del = renderHook(() => useExcluirLotes(), { wrapper });
    await del.result.current.mutateAsync(["a", "b"]);
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/headlines/lotes/excluir", { ids: ["a", "b"] });
  });
});
