/**
 * useLeads.test.ts — unit tests for the Leads list/detail/CRUD hooks.
 *
 * Covers:
 *   1. useLeadsList — calls GET /api/leads with the canonical filter set
 *      encoded as repeated query params + page/sort/order.
 *   2. queryFn never returns undefined — empty page shape on empty response.
 *   3. useLead — unwraps the success_response envelope.
 *   4. useLeadMutations.create/update/remove — correct verbs + paths, and
 *      invalidate the "leads" family on success.
 *
 * Mock strategy: vi.mock @/lib/api (hoisted), matching useMailchimpCampaigns.test.ts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useLead, useLeadMutations, useLeadsList } from "./useLeads";
import { EMPTY_FILTERS } from "./useLeadsFilters";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
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

const makeLead = (id = "lead-1") => ({
  id,
  org_id: "org-1",
  data_entrada: "2026-07-01",
  ano: 2026,
  mes: 7,
  codigo_raw: null,
  codigo_imovel: null,
  empreendimento: null,
  regiao: null,
  origem_id: "src-1",
  origem_raw: "ZAP",
  origem: { id: "src-1", slug: "zap", label: "ZAP", cor: "#ff0000" },
  tipo_lead: "novo" as const,
  cliente_nome: "João Silva",
  contato: "11999999999",
  contato_tipo: "telefone" as const,
  corretor_id: null,
  corretor_raw: null,
  corretor: null,
  anuncio_tier: null,
  status: null,
  observacoes: null,
  follow_up_data: null,
  follow_up_nota: null,
  needs_review: false,
  source_sheet: null,
  source_row: null,
  created_at: "2026-07-01T10:00:00Z",
  updated_at: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockApiGet.mockResolvedValue({
    data: [makeLead("lead-1"), makeLead("lead-2")],
    pagination: { page: 1, page_size: 25, total: 2, total_pages: 1 },
  });
  mockApiPost.mockResolvedValue({ data: makeLead("lead-new") });
  mockApiPatch.mockResolvedValue({ data: makeLead("lead-1") });
  mockApiDelete.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useLeadsList", () => {
  it("calls GET /api/leads with no query string when filters + params are empty", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadsList(EMPTY_FILTERS), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads");
  });

  it("encodes repeated multi-value dims + page/sort/order in the query string", async () => {
    const { Wrapper } = makeWrapper();
    renderHook(
      () =>
        useLeadsList(
          { ...EMPTY_FILTERS, ano: ["2025", "2026"], tipo: ["novo"] },
          { page: 2, pageSize: 50, sort: "cliente_nome", order: "asc" },
        ),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
    const url: string = mockApiGet.mock.calls[0][0];
    const qs = new URLSearchParams(url.split("?")[1]);
    expect(qs.getAll("ano")).toEqual(["2025", "2026"]);
    expect(qs.getAll("tipo")).toEqual(["novo"]);
    expect(qs.get("page")).toBe("2");
    expect(qs.get("page_size")).toBe("50");
    expect(qs.get("sort")).toBe("cliente_nome");
    expect(qs.get("order")).toBe("asc");
  });

  it("queryFn never returns undefined — empty list on empty response", async () => {
    mockApiGet.mockResolvedValue({ data: [], pagination: { page: 1, page_size: 25, total: 0, total_pages: 1 } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadsList(EMPTY_FILTERS), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.data).toEqual([]);
  });
});

describe("useLead", () => {
  it("unwraps the success_response envelope", async () => {
    mockApiGet.mockResolvedValue({ data: makeLead("lead-1") });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLead("lead-1"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/leads/lead-1");
    expect(result.current.data?.id).toBe("lead-1");
  });

  it("is disabled when id is null", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLead(null), { wrapper: Wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiGet).not.toHaveBeenCalled();
  });
});

describe("useLeadMutations", () => {
  it("create fires POST /api/leads and unwraps the envelope", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadMutations(), { wrapper: Wrapper });

    await act(async () => {
      result.current.create.mutate({ data_entrada: "2026-07-01", cliente_nome: "Novo Lead" });
    });

    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/leads",
      expect.objectContaining({ data_entrada: "2026-07-01" }),
    );
    expect(result.current.create.data?.id).toBe("lead-new");
  });

  it("update fires PATCH /api/leads/:id", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadMutations(), { wrapper: Wrapper });

    await act(async () => {
      result.current.update.mutate({ id: "lead-1", body: { cliente_nome: "Atualizado" } });
    });

    await waitFor(() => expect(result.current.update.isSuccess).toBe(true));
    expect(mockApiPatch).toHaveBeenCalledWith("/api/leads/lead-1", { cliente_nome: "Atualizado" });
  });

  it("remove fires DELETE /api/leads/:id", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadMutations(), { wrapper: Wrapper });

    await act(async () => {
      result.current.remove.mutate("lead-1");
    });

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith("/api/leads/lead-1");
  });

  it("mutations invalidate the leads family on success", async () => {
    const { qc, Wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useLeadMutations(), { wrapper: Wrapper });

    await act(async () => {
      result.current.remove.mutate("lead-1");
    });

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["leads"] }));
  });
});
