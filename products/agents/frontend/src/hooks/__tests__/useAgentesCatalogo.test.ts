/** useAgentesCatalogo — `GET /api/agents/catalogo`. Synthetic fixtures only. */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

import { useAgentesCatalogo as useAgentesCatalogoHook } from "@/hooks/useAgentesCatalogo";

beforeEach(() => vi.clearAllMocks());

describe("useAgentesCatalogo", () => {
  it("fetches the catalogo and settles the skeleton", async () => {
    mockGet.mockResolvedValue([
      { key: "agente-a", nome: "Agente A", papel: "sdr", descricao_publica: "Texto sintético.", runtime: "internal", capacidades: ["Cap 1"] },
    ]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useAgentesCatalogoHook(), { wrapper: wrapper(qc) });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(mockGet).toHaveBeenCalledWith("/api/agents/catalogo");
    expect(result.current.showSkeleton).toBe(false);
  });

  it("reports isError on failure", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useAgentesCatalogoHook(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
