/** Roteiros hooks hit the §4.5 endpoints, poll only on real moving status, and invalidate the geracao family. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import {
  algumRoteiroEmAndamento,
  useCriarRoteiro,
  useExcluirRoteiros,
  useFeedbackRoteiro,
  useGerarRoteiro,
  useReprocessarRoteiro,
  useResponderPerguntas,
  useRoteiro,
  useRoteiros,
  useSalvarRoteiro,
} from "./useRoteiros";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

afterEach(() => {
  vi.restoreAllMocks();
  qc.clear();
  Object.values(api).forEach((f) => f.mockReset());
});

describe("useRoteiros (lista)", () => {
  it("lista por marca com busca/offset e expõe showSkeleton/isRefreshing", async () => {
    api.get.mockResolvedValue({ data: { items: [{ id: "r1", status: "completo" }], total: 1 } });
    const { result } = renderHook(() => useRoteiros("m1", " foo ", 20), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.total).toBe(1));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/roteiros?marca_id=m1&limit=20&offset=20&q=foo");
    expect(result.current.showSkeleton).toBe(false);
  });

  it("não consulta sem marca", () => {
    renderHook(() => useRoteiros(null), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
  });

  it("só considera em andamento criando/processando (perguntas espera o usuário)", () => {
    expect(algumRoteiroEmAndamento([{ status: "perguntas" }, { status: "completo" }])).toBe(false);
    expect(algumRoteiroEmAndamento([{ status: "completo" }, { status: "processando" }])).toBe(true);
    expect(algumRoteiroEmAndamento([{ status: "criando" }])).toBe(true);
    expect(algumRoteiroEmAndamento(undefined)).toBe(false);
  });
});

describe("useRoteiro (detalhe)", () => {
  it("busca por id", async () => {
    api.get.mockResolvedValue({ data: { id: "r1", status: "completo" } });
    const { result } = renderHook(() => useRoteiro("r1"), { wrapper });
    await waitFor(() => expect(result.current.data?.id).toBe("r1"));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/roteiros/r1");
  });
});

describe("mutações", () => {
  it("criar → POST /roteiros e invalida", async () => {
    api.post.mockResolvedValue({ data: { id: "r1", status: "criando" } });
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCriarRoteiro(), { wrapper });
    const body = {
      marca_id: "m1",
      headline_texto: "h",
      fonte: "ia" as const,
      duracao: "auto" as const,
      gerar_perguntas: true,
    };
    const r = await result.current.mutateAsync(body);
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/roteiros", body);
    expect(r.id).toBe("r1");
    await waitFor(() => expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao"] }));
  });

  it("perguntas → PUT; gerar → POST com pular_perguntas", async () => {
    api.put.mockResolvedValue({ data: { id: "r1" } });
    api.post.mockResolvedValue({ data: { id: "r1" } });
    const a = renderHook(() => useResponderPerguntas(), { wrapper });
    await a.result.current.mutateAsync({ id: "r1", respostas: [{ id: "p1", resposta: "x" }] });
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/roteiros/r1/perguntas", {
      respostas: [{ id: "p1", resposta: "x" }],
    });
    const g = renderHook(() => useGerarRoteiro(), { wrapper });
    await g.result.current.mutateAsync({ id: "r1", pular_perguntas: true });
    await g.result.current.mutateAsync({ id: "r1" });
    expect(api.post.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ["/api/media-creation/roteiros/r1/gerar", { pular_perguntas: true }],
      ["/api/media-creation/roteiros/r1/gerar", { pular_perguntas: false }],
    ]);
  });

  it("salvar → PUT /roteiros/{id} com expected_versao", async () => {
    api.put.mockResolvedValue({ data: { id: "r1", versao: 3 } });
    const { result } = renderHook(() => useSalvarRoteiro(), { wrapper });
    await result.current.mutateAsync({ id: "r1", conteudo: "novo", expected_versao: 2 });
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/roteiros/r1", { conteudo: "novo", expected_versao: 2 });
  });

  it("feedback, reprocessar e excluir", async () => {
    api.post.mockResolvedValue({ data: { excluidos: 2 } });
    const f = renderHook(() => useFeedbackRoteiro(), { wrapper });
    await f.result.current.mutateAsync({ id: "r1", feedback: "nao_gostei", motivo: "longo" });
    const r = renderHook(() => useReprocessarRoteiro(), { wrapper });
    await r.result.current.mutateAsync({ id: "r1", instrucoes_adicionais: "mais curto" });
    const e = renderHook(() => useExcluirRoteiros(), { wrapper });
    const out = await e.result.current.mutateAsync(["a", "b"]);
    expect(api.post.mock.calls).toEqual([
      ["/api/media-creation/roteiros/r1/feedback", { feedback: "nao_gostei", motivo: "longo" }],
      ["/api/media-creation/roteiros/r1/reprocessar", { instrucoes_adicionais: "mais curto" }],
      ["/api/media-creation/roteiros/excluir", { ids: ["a", "b"] }],
    ]);
    expect(out.excluidos).toBe(2);
  });
});
