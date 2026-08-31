/**
 * Tests for `useDistribuicao` — the refetch-unmount regression (fleet
 * audit, 2026-08-31). Both `usePublicacoes` and `useEficiencia` back a
 * Category A page gate (`Distribuicao.tsx:110` / `:55`); neither is keyed
 * in a way that changes on user input, so no `placeholderData` is added
 * here — only the `loading` formula.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet } }));

let queryState: Record<string, unknown> = {};

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(() => queryState);
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import { useEficiencia, usePublicacoes } from "./useDistribuicao";

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
