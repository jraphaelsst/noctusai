/**
 * Tests for `useDistribuicao` — the refetch-unmount regression (fleet
 * audit, 2026-08-31). Both `usePublicacoes` and `useEficiencia` back a
 * Category A page gate (`Distribuicao.tsx:110` / `:55`); neither is keyed
 * in a way that changes on user input, so no `placeholderData` is added
 * here — only the `loading` formula.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError } from "@noctusai/lib";

const { mockGet, mockInvalidate } = vi.hoisted(() => ({ mockGet: vi.fn(), mockInvalidate: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet } }));

let queryState: Record<string, unknown> = {};

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(() => queryState);
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: mockInvalidate }));
  return { useQuery, useMutation, useQueryClient };
});

import { useEficiencia, useExecutarPublicacao, usePublicacoes } from "./useDistribuicao";
import { INTEGRACOES_QUERY_KEY } from "./useIntegracoes";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("usePublicacoes — loading formula", () => {
  it("REGRESSION: does not report loading mid-refetch once the fila de publicação is on screen", () => {
    queryState = {
      data: [{ id: "pub-1", status: "agendada" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, publicacoes } = usePublicacoes();
    expect(loading).toBe(false);
    expect(publicacoes).toHaveLength(1);
  });

  it("is true on first load", () => {
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    expect(usePublicacoes().loading).toBe(true);
  });
});

describe("useEficiencia — loading formula", () => {
  it("REGRESSION: does not report loading mid-refetch once the BI table is on screen", () => {
    queryState = {
      data: [{ cliente_id: "c1", cliente_nome: "Padaria Sol" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, linhas } = useEficiencia();
    expect(loading).toBe(false);
    expect(linhas).toHaveLength(1);
  });
});

describe("useExecutarPublicacao — credencial_ilegivel invalidates Integrações", () => {
  it("invalidates the integrações query key on a credencial_ilegivel error", () => {
    const hook = useExecutarPublicacao() as unknown as { onError: (e: unknown) => void };
    hook.onError(new ApiError(409, "Token ilegível", { code: "credencial_ilegivel" }));
    expect(mockInvalidate).toHaveBeenCalledWith({ queryKey: INTEGRACOES_QUERY_KEY });
  });

  it("does NOT invalidate integrações on an unrelated error", () => {
    const hook = useExecutarPublicacao() as unknown as { onError: (e: unknown) => void };
    hook.onError(new ApiError(409, "Canal não configurado", { code: "canal_nao_configurado" }));
    expect(mockInvalidate).not.toHaveBeenCalledWith({ queryKey: INTEGRACOES_QUERY_KEY });
  });
});
