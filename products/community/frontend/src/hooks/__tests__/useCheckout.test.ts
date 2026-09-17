/**
 * useCheckout hook tests — community-m2-contract.md §Endpoints#Checkout,
 * amendment A2, product decision P1.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => vi.clearAllMocks());

describe("stripCpfPunctuation / isValidCpfLength", () => {
  it("strips punctuation to digits-only (P1)", async () => {
    const { stripCpfPunctuation } = await import("@/hooks/useCheckout");
    expect(stripCpfPunctuation("123.456.789-01")).toBe("12345678901");
  });

  it("validates exactly 11 digits", async () => {
    const { isValidCpfLength } = await import("@/hooks/useCheckout");
    expect(isValidCpfLength("123.456.789-01")).toBe(true);
    expect(isValidCpfLength("123.456.789")).toBe(false);
    expect(isValidCpfLength("")).toBe(false);
  });
});

describe("useCheckout", () => {
  it("posts to /api/checkout with cpf included for pix", async () => {
    mockPost.mockResolvedValue({
      checkout_url: "https://asaas.example/checkout/abc",
      assinatura_id: "a-1",
      membro_id: "m-1",
      pix_qr: { payload: "000201...", imagem_base64: "iVBORw0KG...", expira_em: "2026-09-17T00:00:00+00:00" },
    });
    const { useCheckout } = await import("@/hooks/useCheckout");
    const { result } = renderHook(() => useCheckout(), { wrapper: wrapper() });

    result.current.mutate({
      plano_id: "p-1",
      metodo: "pix",
      nome: "Ana",
      email: "ana@x.com",
      telefone: "+5511999999999",
      cpf: "12345678901",
      turnstile_token: "tok-abc",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/checkout", {
      plano_id: "p-1",
      metodo: "pix",
      nome: "Ana",
      email: "ana@x.com",
      telefone: "+5511999999999",
      cpf: "12345678901",
      turnstile_token: "tok-abc",
    });
    expect(result.current.data?.pix_qr?.payload).toBe("000201...");
  });

  it("does not send a cpf key at all for cartao (P1 — forbidden, never sent as '')", async () => {
    mockPost.mockResolvedValue({
      checkout_url: "https://checkout.stripe.com/session/xyz",
      assinatura_id: "a-2",
      membro_id: "m-2",
      pix_qr: null,
    });
    const { useCheckout } = await import("@/hooks/useCheckout");
    const { result } = renderHook(() => useCheckout(), { wrapper: wrapper() });

    result.current.mutate({
      plano_id: "p-1",
      metodo: "cartao",
      nome: "Ana",
      email: "ana@x.com",
      telefone: "+5511999999999",
      turnstile_token: "tok-abc",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const sentBody = mockPost.mock.calls[0][1];
    expect(sentBody).not.toHaveProperty("cpf");
  });

  it("amendment A2 — checkout_url:null + status:'verifique_seu_email' resolves as a normal (non-error) outcome", async () => {
    mockPost.mockResolvedValue({
      checkout_url: null,
      assinatura_id: "a-3",
      membro_id: "m-3",
      pix_qr: null,
      status: "verifique_seu_email",
    });
    const { useCheckout } = await import("@/hooks/useCheckout");
    const { result } = renderHook(() => useCheckout(), { wrapper: wrapper() });

    result.current.mutate({
      plano_id: "p-1",
      metodo: "cartao",
      nome: "Ana",
      email: "ativo@x.com",
      telefone: "+5511999999999",
      turnstile_token: "tok-abc",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.checkout_url).toBeNull();
    expect(result.current.data?.status).toBe("verifique_seu_email");
  });
});
