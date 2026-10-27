/** usePermutas — registry query string + the three registry mutations
 *  (request shape AND invalidation of every permutas query). */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { get, post, patch, del } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({ api: { get, post, patch, delete: del } }));

import {
  useAtualizarAtivo,
  useCriarAtivo,
  useMotivosRejeicao,
  useMoverEtapa,
  usePermutaAtivos,
  useRemoverAtivo,
} from "./usePermutas";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}
const keys = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  patch.mockReset();
  del.mockReset();
});

describe("usePermutaAtivos", () => {
  it("sem filtros chama a rota base", async () => {
    get.mockResolvedValue({ items: [{ id: "a" }], total: 1 });
    const { wrapper } = setup();
    const { result } = renderHook(() => usePermutaAtivos(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([{ id: "a" }]));
    expect(get).toHaveBeenCalledWith("/api/permutas");
  });

  it("natureza + incluir inativos vão na query string", async () => {
    get.mockResolvedValue({ items: [], total: 0 });
    const { wrapper } = setup();
    const { result } = renderHook(
      () => usePermutaAtivos("permuta_imovel", { incluirInativos: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith(
      "/api/permutas?natureza=permuta_imovel&incluir_inativos=true",
    );
  });
});

describe("mutações do registro", () => {
  it("criar faz POST /api/permutas e invalida tudo de permutas", async () => {
    post.mockResolvedValue({ id: "novo" });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useCriarAtivo(), { wrapper });
    const body = { natureza: "imovel" as const, imovel_codigo: "ONE1" };
    await result.current.mutateAsync(body);
    expect(post).toHaveBeenCalledWith("/api/permutas", body);
    await waitFor(() => expect(keys(spy)).toContain('["sw","permutas"]'));
  });

  it("atualizar faz PATCH /api/permutas/{id}", async () => {
    patch.mockResolvedValue({ id: "a" });
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useAtualizarAtivo(), { wrapper });
    await result.current.mutateAsync({ ativoId: "a", body: { observacoes: "casa sem escada" } });
    expect(patch).toHaveBeenCalledWith("/api/permutas/a", { observacoes: "casa sem escada" });
    await waitFor(() => expect(keys(spy)).toContain('["sw","permutas"]'));
  });

  it("remover faz DELETE /api/permutas/{id} — os matches caem junto, então invalida tudo", async () => {
    del.mockResolvedValue(undefined);
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useRemoverAtivo(), { wrapper });
    await result.current.mutateAsync("a");
    expect(del).toHaveBeenCalledWith("/api/permutas/a");
    await waitFor(() => expect(keys(spy)).toContain('["sw","permutas"]'));
  });

  it("um erro da API chega ao chamador (nada é gravado; o settle relê a verdade)", async () => {
    post.mockRejectedValue(new Error("[422] natureza é obrigatória."));
    const { spy, wrapper } = setup();
    const { result } = renderHook(() => useCriarAtivo(), { wrapper });
    await expect(
      result.current.mutateAsync({ natureza: "imovel" }),
    ).rejects.toThrow("natureza é obrigatória");
    // Cache-write contract: a failed write rolls back and the settle re-reads the server's truth.
    await waitFor(() => expect(keys(spy)).toContain('["sw","permutas"]'));
  });
});

describe("motivo de rejeição", () => {
  it("useMotivosRejeicao lê o vocabulário do backend", async () => {
    get.mockResolvedValue({ items: [{ codigo: "preco", rotulo: "Preço", exige_detalhe: false }] });
    const { wrapper } = setup();
    const { result } = renderHook(() => useMotivosRejeicao(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(get).toHaveBeenCalledWith("/api/permutas/motivos-rejeicao");
  });

  function comCache(match: Record<string, unknown>) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["sw", "permutas", "matches", undefined], [match]);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    return { qc, wrapper };
  }
  const lido = (qc: QueryClient) =>
    (qc.getQueryData(["sw", "permutas", "matches", undefined]) as Record<string, unknown>[])[0];

  it("rejeitar envia os campos de motivo no PATCH e os grava no cache", async () => {
    const saved = {
      id: "m1", etapa: "rejeitado", motivo_rejeicao: "preco",
      motivo_rejeicao_detalhe: null, motivo_lado: "origem",
    };
    patch.mockResolvedValue(saved);
    const { qc, wrapper } = comCache({ id: "m1", etapa: "sugerido", motivo_rejeicao: null });
    const { result } = renderHook(() => useMoverEtapa(), { wrapper });
    await result.current.mutateAsync({
      matchId: "m1", etapa: "rejeitado", motivo_rejeicao: "preco", motivo_lado: "origem",
    });
    expect(patch).toHaveBeenCalledWith("/api/permutas/matches/m1", {
      etapa: "rejeitado", motivo_rejeicao: "preco", motivo_lado: "origem",
    });
    await waitFor(() => expect(lido(qc).motivo_rejeicao).toBe("preco"));
  });

  it("mover para outra etapa não envia motivo e zera o motivo no cache", async () => {
    patch.mockResolvedValue({ id: "m1", etapa: "avaliacao" });
    const { qc, wrapper } = comCache({
      id: "m1", etapa: "rejeitado", motivo_rejeicao: "preco",
      motivo_rejeicao_detalhe: "x", motivo_lado: "ambos",
    });
    const { result } = renderHook(() => useMoverEtapa(), { wrapper });
    await result.current.mutateAsync({ matchId: "m1", etapa: "avaliacao" });
    expect(patch).toHaveBeenCalledWith("/api/permutas/matches/m1", { etapa: "avaliacao" });
    await waitFor(() => {
      const m = lido(qc);
      expect(m.etapa).toBe("avaliacao");
      expect(m.motivo_rejeicao).toBeNull();
      expect(m.motivo_rejeicao_detalhe).toBeNull();
      expect(m.motivo_lado).toBeNull();
    });
  });
});
