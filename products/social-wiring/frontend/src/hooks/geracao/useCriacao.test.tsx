/** Criação hooks: approval write-through, quota cap, sub-state helpers. Contract-first seams over mocked api. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api, getAuthToken: async () => "t" }));

import {
  criacaoKeys,
  emAndamentoCriacao,
  ESTADO_ROTULO,
  mensagemAprovacao,
  useAprovarEtapa,
  useAtualizarCota,
  useCotaCriacao,
} from "./useCriacao";
import { esteiraKeys } from "./useEsteira";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

afterEach(() => {
  vi.restoreAllMocks();
  qc.clear();
  Object.values(api).forEach((m) => m.mockReset());
});

describe("sub-estado", () => {
  it("só na_fila/gerando/refinando contam como em andamento e todo estado tem rótulo pt-BR", () => {
    expect(emAndamentoCriacao("gerando")).toBe(true);
    expect(emAndamentoCriacao("aguardando_aprovacao")).toBe(false);
    expect(emAndamentoCriacao(null)).toBe(false);
    expect(ESTADO_ROTULO.falhou).toMatch(/falhou/);
  });
});

describe("useAprovarEtapa", () => {
  it("POST /aprovacoes e escreve o post devolvido no detalhe do cache", async () => {
    qc.setQueryData(esteiraKeys.post("p1"), { id: "p1", headline_aprovada: false });
    api.post.mockResolvedValue({ data: { id: "p1", headline_aprovada: true } });
    const { result } = renderHook(() => useAprovarEtapa(), { wrapper });
    await result.current.mutateAsync({ postId: "p1", alvo: "headline", decisao: "aprovar" });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1/aprovacoes", {
      alvo: "headline",
      decisao: "aprovar",
    });
    expect((qc.getQueryData(esteiraKeys.post("p1")) as any).headline_aprovada).toBe(true);
  });

  it("reprovar envia o motivo", async () => {
    api.post.mockResolvedValue({ data: { id: "p1" } });
    const { result } = renderHook(() => useAprovarEtapa(), { wrapper });
    await result.current.mutateAsync({ postId: "p1", alvo: "midia", decisao: "reprovar", motivo: "áudio baixo" });
    expect(api.post.mock.calls[0][1]).toEqual({ alvo: "midia", decisao: "reprovar", motivo: "áudio baixo" });
  });

  it("mensagem de recusa é pt-BR por código e tem fallback", () => {
    expect(mensagemAprovacao({ code: "motivo_obrigatorio" })).toMatch(/Explique/);
    expect(mensagemAprovacao(new Error("x"))).toBe("Não foi possível registrar a decisão.");
  });
});

describe("cota", () => {
  it("lê e grava o limite; a resposta do servidor vai para o cache", async () => {
    api.get.mockResolvedValue({ data: { limite_usd_mes: 15, gasto_usd_mes: 3.2, padrao_usd_mes: 15 } });
    const lida = renderHook(() => useCotaCriacao(), { wrapper });
    expect(lida.result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(lida.result.current.data?.limite_usd_mes).toBe(15));
    api.put.mockResolvedValue({ data: { limite_usd_mes: 30, gasto_usd_mes: 3.2, padrao_usd_mes: 15 } });
    const grava = renderHook(() => useAtualizarCota(), { wrapper });
    await grava.result.current.mutateAsync({ limite_usd_mes: 30 });
    expect(api.put).toHaveBeenCalledWith("/api/media-creation/criacao/cota", { limite_usd_mes: 30 });
    expect((qc.getQueryData(criacaoKeys.cota) as any).limite_usd_mes).toBe(30);
  });
});
