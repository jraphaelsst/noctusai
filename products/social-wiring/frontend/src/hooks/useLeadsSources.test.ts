/**
 * useLeadsSources.test.ts — unit tests for `/api/leads/sources*` (CRUD +
 * alias map + unmapped queue), "Configuração" subtab.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useLeadSourceAliasMutations,
  useLeadSourceAliases,
  useLeadSourceMutations,
  useLeadSourceUnmapped,
  useLeadSources,
} from "./useLeadsSources";

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

const makeSource = (id = "src-1") => ({
  id,
  org_id: "org-1",
  slug: "zap",
  label: "ZAP",
  categoria: "portal" as const,
  cor: "#ff0000",
  ativo: true,
  ordem: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockApiGet.mockResolvedValue({ data: [makeSource()] });
  mockApiPost.mockResolvedValue({ data: makeSource("src-new") });
  mockApiPatch.mockResolvedValue({ data: makeSource() });
  mockApiDelete.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("useLeadSources", () => {
  it("calls GET /api/leads/sources (not paginated) and unwraps data", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSources(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/sources");
    expect(result.current.data).toEqual([makeSource()]);
  });
});

describe("useLeadSourceMutations", () => {
  it("create fires POST /api/leads/sources", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.create.mutate({ label: "ZAP", categoria: "portal" });
    });
    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/leads/sources",
      expect.objectContaining({ label: "ZAP" }),
    );
  });

  it("update fires PATCH /api/leads/sources/:id", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.update.mutate({ id: "src-1", body: { ordem: 2 } });
    });
    await waitFor(() => expect(result.current.update.isSuccess).toBe(true));
    expect(mockApiPatch).toHaveBeenCalledWith("/api/leads/sources/src-1", { ordem: 2 });
  });

  it("remove appends ?reassign_to= when provided (409 handling)", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.remove.mutate({ id: "src-1", reassignTo: "src-2" });
    });
    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith("/api/leads/sources/src-1?reassign_to=src-2");
  });

  it("remove omits the query string when no reassignTo given", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.remove.mutate({ id: "src-1" });
    });
    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith("/api/leads/sources/src-1");
  });
});

describe("useLeadSourceAliases / useLeadSourceUnmapped", () => {
  it("useLeadSourceAliases calls the mapped-list endpoint (no query string)", async () => {
    mockApiGet.mockResolvedValue({ data: [] });
    const { Wrapper } = makeWrapper();
    renderHook(() => useLeadSourceAliases(), { wrapper: Wrapper });
    await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/api/leads/sources/aliases"));
  });

  it("useLeadSourceUnmapped calls ?unmapped=true and returns {alias,count} rows", async () => {
    mockApiGet.mockResolvedValue({ data: [{ alias: "VIVAVREAL", count: 12 }] });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceUnmapped(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/sources/aliases?unmapped=true");
    expect(result.current.data).toEqual([{ alias: "VIVAVREAL", count: 12 }]);
  });
});

describe("useLeadSourceAliasMutations", () => {
  it("upsert fires POST /api/leads/sources/aliases", async () => {
    mockApiPost.mockResolvedValue({
      data: { id: "alias-1", org_id: "org-1", alias: "VIVAVREAL", alias_norm: "VIVAVREAL", source_id: "src-1", origem: "manual", created_at: "" },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceAliasMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.upsert.mutate({ alias: "VIVAVREAL", source_id: "src-1" });
    });
    await waitFor(() => expect(result.current.upsert.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith("/api/leads/sources/aliases", {
      alias: "VIVAVREAL",
      source_id: "src-1",
    });
  });

  it("remove fires DELETE /api/leads/sources/aliases/:id", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadSourceAliasMutations(), { wrapper: Wrapper });
    await act(async () => {
      result.current.remove.mutate("alias-1");
    });
    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith("/api/leads/sources/aliases/alias-1");
  });
});
