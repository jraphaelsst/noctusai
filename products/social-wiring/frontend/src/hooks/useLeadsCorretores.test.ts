/**
 * useLeadsCorretores.test.ts — unit tests for `/api/leads/corretores*`
 * (mirrors `useLeadsSources.test.ts` per §5.2's "mirrors the source-alias
 * endpoints").
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useLeadCorretorAliasMutations,
  useLeadCorretorAliases,
  useLeadCorretorMutations,
  useLeadCorretorUnmapped,
  useLeadCorretores,
} from "./useLeadsCorretores";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

import { api as mockApi } from "@/lib/api";
const mockApiGet = mockApi.get as ReturnType<typeof vi.fn>;
const mockApiPost = mockApi.post as ReturnType<typeof vi.fn>;
const mockApiDelete = (mockApi as any).delete as ReturnType<typeof vi.fn>;
const mockApiPatch = mockApi.patch as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, Wrapper };
}

const makeCorretor = (id = "cor-1") => ({
  id,
  org_id: "org-1",
  nome: "Ana",
  nome_norm: "ANA",
  cor: "#00ff00",
  ativo: true,
  lead_count: 42,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockApiGet.mockResolvedValue({ data: [makeCorretor()] });
  mockApiPost.mockResolvedValue({ data: makeCorretor("cor-new") });
  mockApiPatch.mockResolvedValue({ data: makeCorretor() });
  mockApiDelete.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("useLeadCorretores", () => {
  it("calls GET /api/leads/corretores and unwraps data (each row has lead_count)", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadCorretores(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/corretores");
    expect(result.current.data?.[0].lead_count).toBe(42);
  });
});

describe("useLeadCorretorMutations", () => {
  it("create fires POST /api/leads/corretores", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadCorretorMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.create.mutate({ nome: "Ana" });
    });
    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/leads/corretores",
      expect.objectContaining({ nome: "Ana" }),
    );
  });

  it("remove appends ?reassign_to= when provided", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadCorretorMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.remove.mutate({ id: "cor-1", reassignTo: "cor-2" });
    });
    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith("/api/leads/corretores/cor-1?reassign_to=cor-2");
  });
});

describe("useLeadCorretorAliases / useLeadCorretorUnmapped", () => {
  it("useLeadCorretorAliases calls the mapped-list endpoint", async () => {
    mockApiGet.mockResolvedValue({ data: [] });
    const { Wrapper } = makeWrapper();
    renderHook(() => useLeadCorretorAliases(), { wrapper: Wrapper });
    await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/api/leads/corretores/aliases"));
  });

  it("useLeadCorretorUnmapped calls ?unmapped=true", async () => {
    mockApiGet.mockResolvedValue({ data: [{ alias: "ALE", count: 5 }] });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadCorretorUnmapped(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/corretores/aliases?unmapped=true");
    expect(result.current.data).toEqual([{ alias: "ALE", count: 5 }]);
  });
});

describe("useLeadCorretorAliasMutations", () => {
  it("upsert fires POST /api/leads/corretores/aliases", async () => {
    mockApiPost.mockResolvedValue({
      data: { id: "alias-1", org_id: "org-1", alias: "ALE", alias_norm: "ALE", corretor_id: "cor-1", created_at: "" },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadCorretorAliasMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.upsert.mutate({ alias: "ALE", corretor_id: "cor-1" });
    });
    await waitFor(() => expect(result.current.upsert.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith("/api/leads/corretores/aliases", {
      alias: "ALE",
      corretor_id: "cor-1",
    });
  });

  it("remove fires DELETE /api/leads/corretores/aliases/:id", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadCorretorAliasMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.remove.mutate("alias-1");
    });
    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith("/api/leads/corretores/aliases/alias-1");
  });
});
