/**
 * useApprovals.ts hook tests — contract §E.2
 * (`GET /api/approvals?estado=pendente`, `POST /api/approvals/{id}/decision`).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

const APPROVAL = {
  id: "ap1",
  conversation_id: "c1",
  tool_name: "mcp__academia__kb_escrever",
  tool_input: { slug: "dominio-x" },
  classe: "escrita",
  resumo: "Editar KB dominio-x",
  diff: { antes: "old", depois: "new" },
  decision: "pendente",
  decided_by: null,
  decided_at: null,
  requested_by: "u1",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

beforeEach(() => vi.clearAllMocks());

describe("useApprovals", () => {
  it("GETs /api/approvals?estado=pendente", async () => {
    mockGet.mockResolvedValue({ items: [APPROVAL], total: 1 });
    const { useApprovals } = await import("@/hooks/useApprovals");
    const qc = newClient();
    const { result } = renderHook(() => useApprovals(), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/approvals", { estado: "pendente" });
    expect(result.current.data?.[0].id).toBe("ap1");
  });
});

describe("useDecideApproval", () => {
  it("decide() POSTs {aprovada} and invalidates the approvals list", async () => {
    mockGet.mockResolvedValue({ items: [APPROVAL], total: 1 });
    mockPost.mockResolvedValue({ ...APPROVAL, decision: "aprovada" });
    const { useApprovals, useDecideApproval, APPROVALS_KEY } = await import("@/hooks/useApprovals");
    const qc = newClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const approvals = renderHook(() => useApprovals(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(approvals.result.current.showSkeleton).toBe(false));

    const decide = renderHook(() => useDecideApproval(), { wrapper: wrapper(qc) });
    await decide.result.current.decide("ap1", true);

    expect(mockPost).toHaveBeenCalledWith("/api/approvals/ap1/decision", { aprovada: true });
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: APPROVALS_KEY }));
  });

  it("already_decided rejects with the backend's PT-BR message and still refetches", async () => {
    mockGet.mockResolvedValue({ items: [APPROVAL], total: 1 });
    const { ApiError } = await import("@/lib/errors");
    mockPost.mockRejectedValue(new ApiError(409, "Esta aprovação já foi decidida."));
    const { useDecideApproval, APPROVALS_KEY } = await import("@/hooks/useApprovals");
    const qc = newClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const decide = renderHook(() => useDecideApproval(), { wrapper: wrapper(qc) });

    await expect(decide.result.current.decide("ap1", true)).rejects.toThrow(
      "Esta aprovação já foi decidida.",
    );
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: APPROVALS_KEY }));
  });
});
