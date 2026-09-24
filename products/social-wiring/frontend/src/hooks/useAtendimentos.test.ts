/**
 * useAtendimentos.test.ts — `useArquivarAtendimento` (owner request,
 * 2026-09-24). Mirrors `useLeadsCorretores.test.ts`'s mocking shape
 * (mock `@/lib/api`, real `@tanstack/react-query` via `renderHook`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useArquivarAtendimento } from "./useAtendimentos";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

import { api as mockApi } from "@/lib/api";
const mockApiPatch = mockApi.patch as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, Wrapper, invalidateSpy };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApiPatch.mockResolvedValue({ data: { id: "atd-1", arquivado: true } });
});
afterEach(() => vi.clearAllMocks());

describe("useArquivarAtendimento", () => {
  it("PATCHes /api/atendimentos-venda/{id} with { arquivado: true } — the EXISTING route, no new endpoint", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useArquivarAtendimento(), { wrapper: Wrapper });
    await act(async () => {
      result.current.mutate("atd-1");
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiPatch).toHaveBeenCalledWith("/api/atendimentos-venda/atd-1", {
      arquivado: true,
    });
  });

  it("invalidates the funil board and the atendimentos-venda family on settle", async () => {
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useArquivarAtendimento(), { wrapper: Wrapper });
    await act(async () => {
      result.current.mutate("atd-1");
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["sw-funil"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["atendimentos-venda"] });
  });
});
