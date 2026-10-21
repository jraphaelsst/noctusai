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

describe("useSeedDefaultStages", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts to /api/crm/stages/seed-defaults with no body", async () => {
    mockPost.mockResolvedValue([mockStage]);

    const { useSeedDefaultStages } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useSeedDefaultStages(), {
      wrapper: wrapper(),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/crm/stages/seed-defaults");
    expect(result.current.data).toEqual([mockStage]);
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

// ─── Cache writes: what the user sees, not just which URL was called ────────
// Regression for the live finding of 2026-10-21: a saved note appeared ~2 s
// late because the hook only invalidated (POST, then a full GET). The screen
// must change on the click and settle on the server's row — never wait for a
// refetch. KB § PATTERNS/frontend/mutation-cache-writes.md

function clientAndWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const w = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
}

describe("cache writes", () => {
  beforeEach(() => vi.clearAllMocks());

  it("a new note is in the list while the POST is still in flight, then becomes the server row", async () => {
    const { qc, w } = clientAndWrapper();
    qc.setQueryData(["crm", "activities", "l1"], []);
    let answer!: (v: unknown) => void;
    mockPost.mockReturnValue(new Promise((res) => (answer = res)));
    mockGet.mockReturnValue(new Promise(() => {})); // a refetch must not be needed
    const { useAddActivity } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useAddActivity(), { wrapper: w });

    result.current.mutate({ leadId: "l1", payload: { type: "nota", note: "ligar amanhã" } });
    await waitFor(() =>
      expect(qc.getQueryData<{ note: string }[]>(["crm", "activities", "l1"])).toEqual([
        expect.objectContaining({ note: "ligar amanhã" }),
      ])
    );

    const saved = { id: "a1", org_id: "o1", lead_id: "l1", type: "nota", note: "ligar amanhã", created_by: "u1", created_at: "2026-10-21T18:00:00Z" };
    answer(saved);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(["crm", "activities", "l1"])).toEqual([saved]);
  });

  it("a failed note save takes the stand-in back out", async () => {
    const { qc, w } = clientAndWrapper();
    qc.setQueryData(["crm", "activities", "l1"], []);
    mockPost.mockRejectedValue(new Error("500"));
    mockGet.mockReturnValue(new Promise(() => {}));
    const { useAddActivity } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useAddActivity(), { wrapper: w });
    result.current.mutate({ leadId: "l1", payload: { type: "nota", note: "x" } });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData(["crm", "activities", "l1"])).toEqual([]);
  });

  it("a removed lead leaves the funil on the click", async () => {
    const { qc, w } = clientAndWrapper();
    qc.setQueryData(["crm", "funil"], [{ stage: mockStage, leads: [mockLead] }]);
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { useDeleteLead } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useDeleteLead(), { wrapper: w });
    result.current.mutate("l1");
    await waitFor(() =>
      expect(qc.getQueryData(["crm", "funil"])).toEqual([{ stage: mockStage, leads: [] }])
    );
  });

  it("an edited lead is written into the funil from the PATCH answer", async () => {
    const { qc, w } = clientAndWrapper();
    qc.setQueryData(["crm", "funil"], [{ stage: mockStage, leads: [mockLead] }]);
    mockPatch.mockResolvedValue({ ...mockLead, name: "João S." });
    mockGet.mockReturnValue(new Promise(() => {}));
    const { useUpdateLead } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useUpdateLead(), { wrapper: w });
    result.current.mutate({ id: "l1", data: { name: "João S." } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const funil = qc.getQueryData<{ leads: { name: string }[] }[]>(["crm", "funil"]);
    expect(funil?.[0].leads[0].name).toBe("João S.");
  });
});
