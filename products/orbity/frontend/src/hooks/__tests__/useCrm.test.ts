/**
 * useCrm hook tests.
 *
 * Stubs @/lib/api so no real HTTP is made.
 * Verifies: funil query, stages, lead CRUD, move stage, add activity.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const mockStage = {
  id: "s1",
  org_id: "o1",
  name: "Prospecção",
  position: 1,
  color: "#3b82f6",
  created_at: "2024-01-01T00:00:00Z",
};

const mockLead = {
  id: "l1",
  org_id: "o1",
  name: "João Silva",
  email: "joao@exemplo.com",
  phone: null,
  company: "Empresa X",
  source: "Google",
  stage_id: "s1",
  temperature: "warm" as const,
  qualification_score: 80,
  qualification_source: null,
  value: 5000,
  owner_id: null,
  next_contact: null,
  client_id: null,
  custom_fields: {},
  tags: ["vip"],
  won_at: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("useFunil", () => {
  beforeEach(() => vi.clearAllMocks());

  it("queries /api/crm/funil and returns stage columns", async () => {
    mockGet.mockResolvedValue([{ stage: mockStage, leads: [mockLead] }]);

    const { useFunil } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useFunil(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/crm/funil");
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].stage.name).toBe("Prospecção");
    expect(result.current.data?.[0].leads).toHaveLength(1);
  });
});

describe("useStages", () => {
  beforeEach(() => vi.clearAllMocks());

  it("queries /api/crm/stages", async () => {
    mockGet.mockResolvedValue([mockStage]);

    const { useStages } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useStages(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/crm/stages");
    expect(result.current.data?.[0].name).toBe("Prospecção");
  });
});

describe("useCreateLead", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts to /api/crm/leads with payload", async () => {
    mockPost.mockResolvedValue(mockLead);
    mockGet.mockResolvedValue([{ stage: mockStage, leads: [] }]);

    const { useCreateLead } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useCreateLead(), { wrapper: wrapper() });

    result.current.mutate({ name: "João Silva", stage_id: "s1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/crm/leads", {
      name: "João Silva",
      stage_id: "s1",
    });
  });
});

describe("useDeleteLead", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls DELETE /api/crm/leads/{id}", async () => {
    mockDelete.mockResolvedValue({ ok: true, id: "l1" });
    mockGet.mockResolvedValue([{ stage: mockStage, leads: [] }]);

    const { useDeleteLead } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useDeleteLead(), { wrapper: wrapper() });

    result.current.mutate("l1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith("/api/crm/leads/l1");
  });
});

describe("useMoveLeadStage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("patches /api/crm/leads/{id}/stage with stage_id", async () => {
    mockPatch.mockResolvedValue({ ...mockLead, stage_id: "s2" });
    mockGet.mockResolvedValue([{ stage: mockStage, leads: [] }]);

    const { useMoveLeadStage } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useMoveLeadStage(), { wrapper: wrapper() });

    result.current.mutate({ id: "l1", stage_id: "s2" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith("/api/crm/leads/l1/stage", {
      stage_id: "s2",
    });
  });
});

describe("useAddActivity", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts to /api/crm/leads/{leadId}/activities", async () => {
    const activity = {
      id: "a1",
      org_id: "o1",
      lead_id: "l1",
      type: "nota",
      note: "Primeiro contato",
      created_by: null,
      created_at: "2024-01-01T00:00:00Z",
    };
    mockPost.mockResolvedValue(activity);
    mockGet.mockResolvedValue([]);

    const { useAddActivity } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useAddActivity(), { wrapper: wrapper() });

    result.current.mutate({
      leadId: "l1",
      payload: { type: "nota", note: "Primeiro contato" },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/crm/leads/l1/activities", {
      type: "nota",
      note: "Primeiro contato",
    });
  });
});
