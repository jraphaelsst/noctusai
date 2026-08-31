/**
 * useLeadsAnalytics.test.ts — unit tests for `/api/leads/analytics/*` +
 * `/api/leads/facets`. Every hook accepts the shared `LeadsFilters` — these
 * tests assert the filter set is encoded into the query string and that
 * every response is unwrapped from its `success_response` envelope.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useLeadsByDimension,
  useLeadsFacets,
  useLeadsHeatmap,
  useLeadsSummary,
  useLeadsTimeseries,
} from "./useLeadsAnalytics";
import { EMPTY_FILTERS } from "./useLeadsFilters";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

import { api as mockApi } from "@/lib/api";
const mockApiGet = mockApi.get as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.clearAllMocks());

describe("useLeadsSummary", () => {
  it("calls GET /api/leads/analytics/summary and unwraps data", async () => {
    mockApiGet.mockResolvedValue({
      data: {
        total: 100,
        novos: 60,
        retornos: 40,
        origens_ativas: 12,
        corretores_ativos: 8,
        empreendimentos: 5,
        needs_review: 3,
        periodo: { de: null, ate: null },
        comparativo: { total_anterior: 90, variacao_pct: 11.1 },
        media_diaria: 3.3,
        top_origem: { id: "src-1", label: "ZAP", total: 40, share_pct: 40 },
        top_corretor: { id: "cor-1", nome: "Ana", total: 20 },
      },
    });
    const { result } = renderHook(() => useLeadsSummary(EMPTY_FILTERS), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/analytics/summary");
    expect(result.current.data?.total).toBe(100);
  });

  it("appends the canonical filter set to the query string", async () => {
    mockApiGet.mockResolvedValue({ data: {} });
    renderHook(
      () => useLeadsSummary({ ...EMPTY_FILTERS, origem_id: ["src-1"], needs_review: true }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
    const url: string = mockApiGet.mock.calls[0][0];
    expect(url).toContain("origem_id=src-1");
    expect(url).toContain("needs_review=true");
  });

  it("🔴 keeps the previous summary mounted while a filter change loads (placeholderData, Cat B regression)", async () => {
    // `filters` drives the queryKey for every hook in this file — a
    // filter change swaps to a fresh key with no cached data. Without
    // `placeholderData: (prev) => prev`, `data` would go `undefined` the
    // instant the filter changes, blanking the whole card for one round
    // trip. Representative of the identical fix applied to
    // useLeadsTimeseries / useLeadsByDimension / useLeadsHeatmap below.
    let resolveSecond!: (v: unknown) => void;
    mockApiGet
      .mockResolvedValueOnce({ data: { total: 10 } })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

    const { result, rerender } = renderHook(
      ({ filters }) => useLeadsSummary(filters),
      { wrapper: makeWrapper(), initialProps: { filters: EMPTY_FILTERS } },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect((result.current.data as any)?.total).toBe(10);

    rerender({ filters: { ...EMPTY_FILTERS, needs_review: true } });

    await waitFor(() => expect(result.current.isFetching).toBe(true));
    // The new filter's fetch is in flight, its own cache entry is empty —
    // this MUST still be the previous total, not undefined.
    expect((result.current.data as any)?.total).toBe(10);

    resolveSecond({ data: { total: 20 } });
    await waitFor(() => expect((result.current.data as any)?.total).toBe(20));
  });
});

describe("useLeadsTimeseries", () => {
  it("defaults grain to 'mes' and omits split when not provided", async () => {
    mockApiGet.mockResolvedValue({ data: { grain: "mes", split: null, series_meta: [], points: [] } });
    renderHook(() => useLeadsTimeseries(EMPTY_FILTERS), { wrapper: makeWrapper() });
    await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
    const url: string = mockApiGet.mock.calls[0][0];
    expect(url).toContain("grain=mes");
    expect(url).not.toContain("split=");
  });

  it("passes split when provided", async () => {
    mockApiGet.mockResolvedValue({ data: { grain: "mes", split: "origem", series_meta: [], points: [] } });
    renderHook(() => useLeadsTimeseries(EMPTY_FILTERS, { grain: "dia", split: "origem" }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
    const url: string = mockApiGet.mock.calls[0][0];
    expect(url).toContain("grain=dia");
    expect(url).toContain("split=origem");
  });
});

describe("useLeadsByDimension", () => {
  it("requires dim + optional limit", async () => {
    mockApiGet.mockResolvedValue({ data: { dim: "origem", total: 0, buckets: [] } });
    renderHook(() => useLeadsByDimension(EMPTY_FILTERS, { dim: "corretor", limit: 10 }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
    const url: string = mockApiGet.mock.calls[0][0];
    expect(url).toContain("dim=corretor");
    expect(url).toContain("limit=10");
  });
});

describe("useLeadsHeatmap", () => {
  it("calls GET /api/leads/analytics/heatmap and unwraps data", async () => {
    mockApiGet.mockResolvedValue({ data: { anos: [2025, 2026], cells: {}, max: 10 } });
    const { result } = renderHook(() => useLeadsHeatmap(EMPTY_FILTERS), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/analytics/heatmap");
    expect(result.current.data?.anos).toEqual([2025, 2026]);
  });
});

describe("useLeadsFacets", () => {
  it("calls GET /api/leads/facets and unwraps data", async () => {
    mockApiGet.mockResolvedValue({
      data: { empreendimentos: [{ value: "Bosque", count: 5 }], regioes: [], anos: [2025] },
    });
    const { result } = renderHook(() => useLeadsFacets(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/facets");
    expect(result.current.data?.anos).toEqual([2025]);
  });
});
