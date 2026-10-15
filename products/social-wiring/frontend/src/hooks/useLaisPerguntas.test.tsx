import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { mensagemErroPerguntas, useLaisContato, useLaisPerguntas, useSalvarPerguntas } from "./useLaisPerguntas";

const wrap = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};
beforeEach(() => { api.get.mockReset(); api.put.mockReset(); });

describe("useLaisPerguntas", () => {
  it("unwraps the envelope", async () => {
    api.get.mockResolvedValue({ data: { catalogo: [], limites: { max_ativas: 8, max_qualificatorias: 5 } } });
    const { result } = renderHook(() => useLaisPerguntas(), { wrapper: wrap() });
    await waitFor(() => expect(result.current.data?.limites.max_ativas).toBe(8));
  });

  it("PUT writes the returned catalogue into the cache", async () => {
    const novo = { data: { catalogo: [], limites: { max_ativas: 8, max_qualificatorias: 5 } } };
    api.put.mockResolvedValue(novo);
    const { result } = renderHook(() => useSalvarPerguntas(), { wrapper: wrap() });
    result.current.mutate([{ chave: "objetivo", qualificatoria: false }]);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.put).toHaveBeenCalledWith("/api/lais/perguntas", { selecao: [{ chave: "objetivo", qualificatoria: false }] });
  });

  it("contato is disabled without ids and encodes the chat id", async () => {
    const off = renderHook(() => useLaisContato(null, null), { wrapper: wrap() });
    expect(off.result.current.fetchStatus).toBe("idle");
    api.get.mockResolvedValue({ data: { contato: null, slots: {}, interacao_atual: null } });
    renderHook(() => useLaisContato("c1", "5511@c.us"), { wrapper: wrap() });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/lais/contatos/c1/5511%40c.us"));
  });

  it("maps refusal codes", () => {
    const e = (code: string) => ({ body: { error: { code } } });
    expect(mensagemErroPerguntas(e("objetivo_obrigatorio"), "f")).toContain("essencial");
    expect(mensagemErroPerguntas(e("limite_qualificatorias"), "f")).toContain("qualificatórias");
  });
});
