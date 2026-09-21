/**
 * useClientsKe.ts hook tests — Agent Studio CONTRACT.md §D2 (FE-KE's own
 * reader — see the hook file's header for why).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

beforeEach(() => vi.clearAllMocks());

describe("useClientsKe", () => {
  it("GETs the client list (omits entradas, carries total_entradas)", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "cl1", slug: "cliente-a", nome: "Cliente A", resumo: "...", ativo: true, total_entradas: 4 }] });
    const { useClientsKe } = await import("@/hooks/studio/useClientsKe");
    const qc = newClient();
    const { result } = renderHook(() => useClientsKe("isaia"), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/clients");
    expect(result.current.data?.[0].total_entradas).toBe(4);
  });
});

describe("useClientKe", () => {
  it("GETs one client's detail (includes entradas)", async () => {
    mockGet.mockResolvedValue({ id: "cl1", slug: "cliente-a", nome: "Cliente A", resumo: "...", ativo: true, entradas: [{ id: "e1", tipo: "marca", titulo: "Tom", conteudo: "...", status: "ativo", created_at: "t" }] });
    const { useClientKe } = await import("@/hooks/studio/useClientsKe");
    const qc = newClient();
    const { result } = renderHook(() => useClientKe("isaia", "cl1"), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/clients/cl1");
    expect(result.current.data?.entradas).toHaveLength(1);
  });

  it("is disabled with no clientId", async () => {
    const { useClientKe } = await import("@/hooks/studio/useClientsKe");
    const qc = newClient();
    renderHook(() => useClientKe("isaia", null), { wrapper: wrapper(qc) });
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("useCreateClientEntry", () => {
  it("POSTs {tipo, titulo, conteudo} to the client's entries endpoint", async () => {
    mockPost.mockResolvedValue({ id: "e2" });
    const { useCreateClientEntry } = await import("@/hooks/studio/useClientsKe");
    const qc = newClient();
    const { result } = renderHook(() => useCreateClientEntry("isaia", "cl1"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ tipo: "trava", titulo: "Sem preço na bio", conteudo: "Nunca citar preço." });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/clients/cl1/entries", {
      tipo: "trava",
      titulo: "Sem preço na bio",
      conteudo: "Nunca citar preço.",
    });
  });
});

describe("useUpdateClientKe", () => {
  it("PATCHes the client and updates both the detail and list caches", async () => {
    mockPatch.mockResolvedValue({ id: "cl1", slug: "cliente-a", nome: "Cliente A", resumo: "novo resumo", ativo: true, entradas: [] });
    const { useUpdateClientKe } = await import("@/hooks/studio/useClientsKe");
    const qc = newClient();
    const { result } = renderHook(() => useUpdateClientKe("isaia"), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ clientId: "cl1", patch: { resumo: "novo resumo" } });
    expect(mockPatch).toHaveBeenCalledWith("/api/studio/agents/isaia/clients/cl1", { resumo: "novo resumo" });
  });
});
