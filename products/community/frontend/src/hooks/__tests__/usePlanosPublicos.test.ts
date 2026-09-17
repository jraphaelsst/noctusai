/**
 * usePlanosPublicos hook tests — community-m2-contract.md amendment A17.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => vi.clearAllMocks());

describe("usePlanosPublicos", () => {
  it("fetches the PUBLIC /api/planos/publicos endpoint (A17), not module 1's /api/planos", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          id: "p-1",
          nome: "Círculo",
          descricao: null,
          preco_centavos: 9900,
          ciclo: "mensal",
          beneficios: { feed: true, forum: true, chat: false, eventos: false },
          metodos_disponiveis: ["cartao"],
        },
      ],
      total: 1,
    });
    const { usePlanosPublicos } = await import("@/hooks/usePlanosPublicos");
    const { result } = renderHook(() => usePlanosPublicos(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/planos/publicos");
    expect(result.current.data?.items[0].metodos_disponiveis).toEqual(["cartao"]);
  });

  it("never assumes gateway refs or membros_ativos are present (narrower than Plano)", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          id: "p-2",
          nome: "Sem gateway",
          descricao: null,
          preco_centavos: 4900,
          ciclo: "mensal",
          beneficios: { feed: true, forum: false, chat: false, eventos: false },
          metodos_disponiveis: [],
        },
      ],
      total: 1,
    });
    const { usePlanosPublicos } = await import("@/hooks/usePlanosPublicos");
    const { result } = renderHook(() => usePlanosPublicos(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const item = result.current.data?.items[0] as unknown as Record<string, unknown>;
    expect(item.metodos_disponiveis).toEqual([]);
    expect(item).not.toHaveProperty("ref_externo");
    expect(item).not.toHaveProperty("membros_ativos");
  });
});
