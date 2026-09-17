/**
 * usePagamentos hook tests — community-m2-contract.md
 * §Endpoints#Manager-+-member-views, amendments A16/P3 (admin-only).
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

describe("usePagamentos", () => {
  it("fetches /api/pagamentos with the bare {items,total} envelope", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          id: "pg-1",
          membro_id: "m-1",
          membro_nome: "Ana",
          assinatura_id: "a-1",
          gateway: "stripe",
          cobranca_externa_id: "ch_123",
          valor_centavos: 9900,
          metodo: "cartao",
          estado: "pago",
          pago_em: "2026-09-16T20:00:00+00:00",
          vencimento: null,
          url_fatura: "https://stripe.example/invoice/123",
          pix_payload: null,
          pix_imagem_base64: null,
          created_at: "2026-09-16T20:00:00+00:00",
        },
      ],
      total: 1,
    });
    const { usePagamentos } = await import("@/hooks/usePagamentos");
    const { result } = renderHook(() => usePagamentos({ membro_id: "m-1" }), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/pagamentos", { membro_id: "m-1" });
    expect(result.current.data?.items[0].valor_centavos).toBe(9900);
  });

  it("A16/P3 — a moderador's strict 403 surfaces as the hook's error, not a crash", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(403, "Apenas administradores podem ver os pagamentos."));
    const { usePagamentos } = await import("@/hooks/usePagamentos");
    const { result } = renderHook(() => usePagamentos(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as InstanceType<typeof ApiError>).status).toBe(403);
  });
});
