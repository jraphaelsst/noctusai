/**
 * useAssinaturas hook tests — community-m2-contract.md
 * §Endpoints#Manager-+-member-views, amendment P3.
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
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => vi.clearAllMocks());

describe("useAssinaturas", () => {
  it("fetches /api/assinaturas with the bare {items,total} envelope", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          id: "a-1",
          membro_id: "m-1",
          membro_nome: "Ana",
          plano_id: "p-1",
          plano_nome: "Círculo",
          gateway: "stripe",
          estado: "ativa",
          metodo: "cartao",
          ciclo: "mensal",
          assinatura_externa_id: "sub_123",
          iniciada_em: "2026-09-01T00:00:00+00:00",
          ativa_em: "2026-09-02T00:00:00+00:00",
          cancelada_em: null,
        },
      ],
      total: 1,
    });
    const { useAssinaturas } = await import("@/hooks/useAssinaturas");
    const { result } = renderHook(() => useAssinaturas({ membro_id: "m-1" }), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/assinaturas", { membro_id: "m-1" });
    expect(result.current.data?.items[0].membro_nome).toBe("Ana");
  });

  it("P3 — a moderador-redacted item (no assinatura_externa_id) does not break the shape", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          id: "a-2",
          membro_id: "m-2",
          membro_nome: "Bia",
          plano_id: "p-1",
          plano_nome: "Círculo",
          gateway: "asaas",
          estado: "inadimplente",
          metodo: "pix",
          ciclo: "mensal",
          // assinatura_externa_id intentionally absent — moderador shape.
          iniciada_em: "2026-09-01T00:00:00+00:00",
          ativa_em: null,
          cancelada_em: null,
        },
      ],
      total: 1,
    });
    const { useAssinaturas } = await import("@/hooks/useAssinaturas");
    const { result } = renderHook(() => useAssinaturas(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0].assinatura_externa_id).toBeUndefined();
  });
});

describe("useCancelarAssinatura", () => {
  it("posts {motivo} to /api/assinaturas/{id}/cancelar", async () => {
    mockPost.mockResolvedValue({
      id: "a-1",
      estado: "cancelada",
    });
    const { useCancelarAssinatura } = await import("@/hooks/useAssinaturas");
    const { result } = renderHook(() => useCancelarAssinatura(), { wrapper: wrapper() });

    result.current.mutate({ id: "a-1", motivo: "Solicitado pelo membro" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/assinaturas/a-1/cancelar", { motivo: "Solicitado pelo membro" });
  });
});
