/**
 * Financial hooks (the Orbity layer over the seed organs) -- render tests.
 *
 * Mocking pattern: vi.mock factories cannot reference module-scope variables (vitest hoists them), so the shared mock
 * functions come from vi.hoisted(). localStorage is provisioned by the seed vitest.setup.ts.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { mockGet, mockPost, mockToast } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockToast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost } }));
vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: { id: "u1", email: "test@orbity.app" } }),
  api: { get: mockGet, post: mockPost },
}));
vi.mock("sonner", () => ({ toast: mockToast }));

import { useCashFlow, useCharges, useCreateExtraCharge, useGatewayStatus, useRequeueCharge } from "@/hooks/useFinancial";

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client }, children);
}

const CASH_FLOW = {
  reference_month: "2026-06-01", paid_revenues: 5000, paid_expenses: 1200, net: 3800, pending_revenues: 1500, overdue_revenues: 0,
};

const CHARGE = {
  entry_id: "e1", client_id: "c1", client_name: "Acme LTDA", contract_id: null, description: "Gestão — 10/2026", due_date: "2026-10-20",
  amount_cents: 150000, settled_cents: 0, entry_status: "open", overdue: false, generation_status: "generated", generation_attempts: 1,
  last_error: null, next_attempt_at: null, gateway: "asaas", billing_method: "boleto", external_id: "pay_1", invoice_url: "https://asaas.test/i/1",
  pix_payload: null, preserved_after_deactivation: false, gateway_cancel_status: null, gateway_cancel_error: null,
};

beforeEach(() => vi.clearAllMocks());

describe("useCashFlow", () => {
  it("converts YYYY-MM to the first day the backend expects and exposes the summary", async () => {
    mockGet.mockResolvedValue(CASH_FLOW);
    const { result } = renderHook(() => useCashFlow("2026-06"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/financial/cash-flow/2026-06-01");
    expect(result.current.data?.net).toBe(3800);
  });

  it("surfaces a failure (no silent zero)", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao calcular fluxo de caixa"));
    const { result } = renderHook(() => useCashFlow("2026-06"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("fluxo de caixa");
  });

  it("is disabled when the month is empty -- no fetch", () => {
    const { result } = renderHook(() => useCashFlow(""), { wrapper: makeWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("useGatewayStatus", () => {
  it("reads whether a gateway is configured", async () => {
    mockGet.mockResolvedValue({ gateway: "asaas", configured: false });
    const { result } = renderHook(() => useGatewayStatus(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/financial/gateway");
    expect(result.current.data?.configured).toBe(false);
  });
});

describe("useCharges", () => {
  it("passes the filters and pagination to the backend", async () => {
    mockGet.mockResolvedValue({ items: [CHARGE], total: 1, page: 2, page_size: 25 });
    const { result } = renderHook(() => useCharges({ generation_status: "failed", page: 2, page_size: 25 }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/financial/charges", { client_id: undefined, generation_status: "failed", page: 2, page_size: 25 });
    expect(result.current.data?.items[0].invoice_url).toContain("asaas");
  });

  it("surfaces an error", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar cobranças"));
    const { result } = renderHook(() => useCharges(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("cobranças");
  });
});

describe("useRequeueCharge", () => {
  it("posts to the generate route and tells the operator", async () => {
    mockPost.mockResolvedValue(CHARGE);
    const { result } = renderHook(() => useRequeueCharge(), { wrapper: makeWrapper() });
    await act(async () => { await result.current.mutateAsync("e1"); });
    expect(mockPost).toHaveBeenCalledWith("/api/financial/charges/e1/generate", {});
    expect(mockToast.success).toHaveBeenCalled();
  });

  it("shows the backend's reason when the gateway is not configured", async () => {
    mockPost.mockRejectedValue(new Error("Gateway de cobrança não configurado para esta organização."));
    const { result } = renderHook(() => useRequeueCharge(), { wrapper: makeWrapper() });
    await act(async () => { await result.current.mutateAsync("e1").catch(() => undefined); });
    expect(mockToast.error).toHaveBeenCalledWith(expect.any(String), { description: "Gateway de cobrança não configurado para esta organização." });
  });
});

describe("useCreateExtraCharge", () => {
  it("posts the one-off charge", async () => {
    mockPost.mockResolvedValue(CHARGE);
    const { result } = renderHook(() => useCreateExtraCharge(), { wrapper: makeWrapper() });
    const body = { client_id: "c1", description: "Setup", amount_cents: 50000, due_date: "2026-10-30" };
    await act(async () => { await result.current.mutateAsync(body); });
    expect(mockPost).toHaveBeenCalledWith("/api/financial/charges", body);
  });
});
