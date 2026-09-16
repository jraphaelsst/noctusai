/**
 * usePlanos hook tests — community-m1-contract.md §Endpoints#Planos.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: mockPatch, delete: mockDelete },
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const PLANO = {
  id: "p-1",
  nome: "Círculo",
  descricao: null,
  preco_centavos: 9900,
  ciclo: "mensal" as const,
  entitlements: {
    feed: true,
    forum: true,
    chat: true,
    eventos: true,
    conteudo_ids: [],
    grupos_whatsapp: [],
    conteudo_todos: false,
  },
  ativo: true,
  ordem: 0,
  membros_ativos: 12,
  created_at: "2026-09-16T20:00:00+00:00",
  updated_at: "2026-09-16T20:00:00+00:00",
};

beforeEach(() => vi.clearAllMocks());

describe("usePlanos", () => {
  it("fetches /api/planos with the bare {items,total} envelope", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    const { usePlanos } = await import("@/hooks/usePlanos");
    const { result } = renderHook(() => usePlanos({ page: 1, page_size: 50 }), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/planos", { page: 1, page_size: 50 });
    expect(result.current.data?.items[0].nome).toBe("Círculo");
    expect(result.current.data?.total).toBe(1);
  });
});

describe("useCreatePlano", () => {
  it("posts to /api/planos", async () => {
    mockPost.mockResolvedValue(PLANO);
    const { useCreatePlano } = await import("@/hooks/usePlanos");
    const { result } = renderHook(() => useCreatePlano(), { wrapper: wrapper() });

    result.current.mutate({ nome: "Círculo", preco_centavos: 9900, ciclo: "mensal" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/planos", {
      nome: "Círculo",
      preco_centavos: 9900,
      ciclo: "mensal",
    });
  });
});

describe("useUpdatePlano", () => {
  it("patches /api/planos/{id}", async () => {
    mockPatch.mockResolvedValue({ ...PLANO, nome: "Círculo VIP" });
    const { useUpdatePlano } = await import("@/hooks/usePlanos");
    const { result } = renderHook(() => useUpdatePlano(), { wrapper: wrapper() });

    result.current.mutate({ id: "p-1", nome: "Círculo VIP" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith("/api/planos/p-1", { nome: "Círculo VIP" });
  });
});

describe("useDeletePlano", () => {
  it("soft-deletes via DELETE /api/planos/{id}", async () => {
    mockDelete.mockResolvedValue(undefined);
    const { useDeletePlano } = await import("@/hooks/usePlanos");
    const { result } = renderHook(() => useDeletePlano(), { wrapper: wrapper() });

    result.current.mutate("p-1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith("/api/planos/p-1");
  });
});
