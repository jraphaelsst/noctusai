/**
 * useGatewayRefs hooks tests — community-m2-contract.md
 * §Endpoints#Gateway-refs.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: mockPut, patch: vi.fn(), delete: mockDelete },
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => vi.clearAllMocks());

describe("useGatewayRefs", () => {
  it("fetches /api/planos/{plano_id}/gateway-refs", async () => {
    mockGet.mockResolvedValue({
      items: [{ plano_id: "p-1", gateway: "stripe", ref_externo: "price_123", updated_at: "2026-09-16T20:00:00+00:00" }],
      total: 1,
    });
    const { useGatewayRefs } = await import("@/hooks/useGatewayRefs");
    const { result } = renderHook(() => useGatewayRefs("p-1"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/planos/p-1/gateway-refs");
    expect(result.current.data?.items[0].ref_externo).toBe("price_123");
  });

  it("does not fetch when planoId is falsy", async () => {
    const { useGatewayRefs } = await import("@/hooks/useGatewayRefs");
    renderHook(() => useGatewayRefs(undefined), { wrapper: wrapper() });
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("useSetGatewayRef", () => {
  it("PUTs {ref_externo} to /api/planos/{plano_id}/gateway-refs/{gateway} (upsert)", async () => {
    mockPut.mockResolvedValue({
      plano_id: "p-1",
      gateway: "asaas",
      ref_externo: "asaas-plan-1",
      updated_at: "2026-09-16T20:00:00+00:00",
    });
    const { useSetGatewayRef } = await import("@/hooks/useGatewayRefs");
    const { result } = renderHook(() => useSetGatewayRef("p-1"), { wrapper: wrapper() });

    result.current.mutate({ gateway: "asaas", ref_externo: "asaas-plan-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith("/api/planos/p-1/gateway-refs/asaas", { ref_externo: "asaas-plan-1" });
  });
});

describe("useDeleteGatewayRef", () => {
  it("DELETEs /api/planos/{plano_id}/gateway-refs/{gateway}", async () => {
    mockDelete.mockResolvedValue(null);
    const { useDeleteGatewayRef } = await import("@/hooks/useGatewayRefs");
    const { result } = renderHook(() => useDeleteGatewayRef("p-1"), { wrapper: wrapper() });

    result.current.mutate("stripe");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith("/api/planos/p-1/gateway-refs/stripe");
  });
});
