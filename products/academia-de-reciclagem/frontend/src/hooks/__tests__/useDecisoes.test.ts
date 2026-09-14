/**
 * useDecisoes hook tests — contract §B.2.
 *
 * Verifies list/detail GETs, the create POST, and the supersede flow:
 * `POST /api/decisions/{codigo}/supersede` → `{nova, substituida}`.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const D10 = {
  codigo: "D-10",
  titulo: "Usar Postgres",
  contexto: "Precisamos de um banco relacional",
  decisao: "Usar Postgres",
  motivo: "Já usado no resto da plataforma",
  alternativas_rejeitadas: "MongoDB",
  data: "2026-08-01",
  estado: "vigente" as const,
  substitui: null,
  superseded_by: null,
  relacionadas: [],
};

beforeEach(() => vi.clearAllMocks());

describe("useDecisoesList", () => {
  it("queries GET /api/decisions with estado filter", async () => {
    mockGet.mockResolvedValue({ items: [D10], total: 1 });
    const { useDecisoesList } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useDecisoesList("vigente"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/decisions", { estado: "vigente" });
    expect(result.current.data?.items[0].codigo).toBe("D-10");
  });

  it("queries GET /api/decisions without a filter when estado is omitted", async () => {
    mockGet.mockResolvedValue({ items: [D10], total: 1 });
    const { useDecisoesList } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useDecisoesList(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/decisions", undefined);
  });
});

describe("useDecisao", () => {
  it("queries GET /api/decisions/{codigo}", async () => {
    mockGet.mockResolvedValue(D10);
    const { useDecisao } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useDecisao("D-10"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/decisions/D-10");
  });
});

describe("useCreateDecisao", () => {
  it("posts to /api/decisions with the create payload", async () => {
    mockPost.mockResolvedValue(D10);
    const { useCreateDecisao } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useCreateDecisao(), { wrapper: wrapper() });

    result.current.mutate({
      titulo: "Usar Postgres",
      decisao: "Usar Postgres",
      motivo: "Já usado no resto da plataforma",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/decisions", {
      titulo: "Usar Postgres",
      decisao: "Usar Postgres",
      motivo: "Já usado no resto da plataforma",
    });
  });
});

describe("useSupersedeDecisao", () => {
  it("posts to /api/decisions/{codigo}/supersede and returns {nova, substituida}", async () => {
    const nova = { ...D10, codigo: "D-21", substitui: "D-10" };
    const substituida = { ...D10, estado: "superseded" as const, superseded_by: "D-21" };
    mockPost.mockResolvedValue({ nova, substituida });

    const { useSupersedeDecisao } = await import("@/hooks/useDecisoes");
    const { result } = renderHook(() => useSupersedeDecisao("D-10"), { wrapper: wrapper() });

    result.current.mutate({
      titulo: "Usar Postgres 16",
      decisao: "Migrar para Postgres 16",
      motivo: "Suporte a recursos novos",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/decisions/D-10/supersede", {
      titulo: "Usar Postgres 16",
      decisao: "Migrar para Postgres 16",
      motivo: "Suporte a recursos novos",
    });
    expect(result.current.data?.nova.codigo).toBe("D-21");
    expect(result.current.data?.nova.substitui).toBe("D-10");
    expect(result.current.data?.substituida.codigo).toBe("D-10");
    expect(result.current.data?.substituida.estado).toBe("superseded");
    expect(result.current.data?.substituida.superseded_by).toBe("D-21");
  });
});
