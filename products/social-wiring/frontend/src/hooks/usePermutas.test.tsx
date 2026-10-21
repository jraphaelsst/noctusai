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
