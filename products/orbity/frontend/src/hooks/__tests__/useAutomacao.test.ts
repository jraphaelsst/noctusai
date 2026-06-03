/**
 * Automacao hooks — render tests for all four query states:
 *   loading → success (with data) → success (empty list) → error
 *
 * Covers: useFlows, useSteps, useExecutions, mutations (create/update/delete/trigger/run-due).
 *
 * Mocking pattern: vi.hoisted() so shared mock functions are initialized
 * before vi.mock factories run (vitest hoists vi.mock above all declarations).
 *
 * Note: localStorage is provisioned by the seed vitest.setup.ts — not re-polyfilled here.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Shared mocks via vi.hoisted
// ---------------------------------------------------------------------------

const { mockGet, mockPost, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
}));

vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: { id: "u1", email: "test@orbity.app" } }),
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// ---------------------------------------------------------------------------
// Static import of hooks under test (mocks already hoisted)
// ---------------------------------------------------------------------------

import {
  useFlows,
  useSteps,
  useExecutions,
  useCreateFlow,
  useUpdateFlow,
  useDeleteFlow,
  useCreateStep,
  useUpdateStep,
  useDeleteStep,
  useTriggerFlow,
  useCancelExecution,
  useRunDue,
} from "@/hooks/useAutomacao";

// ---------------------------------------------------------------------------
// Wrapper factory
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const FLOW_ITEM = {
  id: "flow-1",
  org_id: "org-1",
  name: "Boas-vindas novos leads",
  trigger_type: "lead_created" as const,
  trigger_config: {},
  active: true,
  schedule_window: {},
  stop_rules: {},
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const STEP_ITEM = {
  id: "step-1",
  org_id: "org-1",
  flow_id: "flow-1",
  ord: 0,
  step_type: "send_message" as const,
  config: { template: "Ola {{lead_name}}!" },
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const EXECUTION_ITEM = {
  id: "exec-1",
  org_id: "org-1",
  flow_id: "flow-1",
  lead_id: "lead-uuid-123",
  status: "running" as const,
  current_step_ord: 0,
  started_at: "2026-06-01T10:00:00Z",
  next_action_at: "2026-06-01T11:00:00Z",
  context: {},
  error_detail: null,
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-01T10:00:00Z",
};

// ---------------------------------------------------------------------------
// Tests: useFlows
// ---------------------------------------------------------------------------

describe("useFlows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state — query is in-flight", () => {
    mockGet.mockImplementation(() => new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useFlows(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("success state — returns flows list", async () => {
    mockGet.mockResolvedValue([FLOW_ITEM]);
    const { result } = renderHook(() => useFlows(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/automation/flows",
      expect.objectContaining({ active_only: false }),
    );
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("Boas-vindas novos leads");
    expect(result.current.data?.[0].trigger_type).toBe("lead_created");
    expect(result.current.data?.[0].active).toBe(true);
  });

  it("empty state — returns empty array", async () => {
    mockGet.mockResolvedValue([]);
    const { result } = renderHook(() => useFlows(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });

  it("error state — exposes error message", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar fluxos"));
    const { result } = renderHook(() => useFlows(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Falha ao listar fluxos");
    expect(result.current.data).toBeUndefined();
  });

  it("active_only filter forwarded to API", async () => {
    mockGet.mockResolvedValue([FLOW_ITEM]);
    const { result } = renderHook(() => useFlows(true), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/automation/flows",
      expect.objectContaining({ active_only: true }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: useSteps
// ---------------------------------------------------------------------------

describe("useSteps", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state when flowId provided", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useSteps("flow-1"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("success state — returns ordered steps", async () => {
    mockGet.mockResolvedValue([STEP_ITEM]);
    const { result } = renderHook(() => useSteps("flow-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/automation/flows/flow-1/steps",
    );
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].step_type).toBe("send_message");
    expect(result.current.data?.[0].ord).toBe(0);
    expect(result.current.data?.[0].config).toEqual({
      template: "Ola {{lead_name}}!",
    });
  });

  it("empty state — returns empty array", async () => {
    mockGet.mockResolvedValue([]);
    const { result } = renderHook(() => useSteps("flow-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });

  it("error state — exposes error", async () => {
    mockGet.mockRejectedValue(new Error("502 Bad Gateway"));
    const { result } = renderHook(() => useSteps("flow-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("502");
  });

  it("disabled when flowId is null — no fetch", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useSteps(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Tests: useExecutions
// ---------------------------------------------------------------------------

describe("useExecutions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("success state — returns executions with correct shape", async () => {
    mockGet.mockResolvedValue([EXECUTION_ITEM]);
    const { result } = renderHook(() => useExecutions(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/automation/executions",
      expect.objectContaining({ lead_id: undefined }),
    );
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].status).toBe("running");
    expect(result.current.data?.[0].current_step_ord).toBe(0);
    expect(result.current.data?.[0].lead_id).toBe("lead-uuid-123");
  });

  it("empty state — returns empty array", async () => {
    mockGet.mockResolvedValue([]);
    const { result } = renderHook(() => useExecutions(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });

  it("error state — surfaces error", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar execucoes"));
    const { result } = renderHook(() => useExecutions(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Tests: useCreateFlow
// ---------------------------------------------------------------------------

describe("useCreateFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/automation/flows with correct payload", async () => {
    mockPost.mockResolvedValue(FLOW_ITEM);
    const { result } = renderHook(() => useCreateFlow(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({
        name: "Boas-vindas novos leads",
        trigger_type: "lead_created",
        active: true,
      });
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/automation/flows",
      expect.objectContaining({
        name: "Boas-vindas novos leads",
        trigger_type: "lead_created",
      }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("surfaces error on failure", async () => {
    mockPost.mockRejectedValue(new Error("Falha ao criar fluxo"));
    const { result } = renderHook(() => useCreateFlow(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      try {
        await result.current.mutateAsync({
          name: "Fluxo teste",
          trigger_type: "manual",
        });
      } catch {
        // expected
      }
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Falha ao criar fluxo");
  });
});

// ---------------------------------------------------------------------------
// Tests: useUpdateFlow
// ---------------------------------------------------------------------------

describe("useUpdateFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls PATCH /api/automation/flows/:id", async () => {
    mockPatch.mockResolvedValue({ ...FLOW_ITEM, active: false });
    const { result } = renderHook(() => useUpdateFlow(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ id: "flow-1", active: false });
    });
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/automation/flows/flow-1",
      expect.objectContaining({ active: false }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useDeleteFlow
// ---------------------------------------------------------------------------

describe("useDeleteFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls DELETE /api/automation/flows/:id", async () => {
    mockDelete.mockResolvedValue({ ok: true, id: "flow-1" });
    const { result } = renderHook(() => useDeleteFlow(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync("flow-1");
    });
    expect(mockDelete).toHaveBeenCalledWith("/api/automation/flows/flow-1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useCreateStep
// ---------------------------------------------------------------------------

describe("useCreateStep", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/automation/flows/:flowId/steps", async () => {
    mockPost.mockResolvedValue(STEP_ITEM);
    const { result } = renderHook(() => useCreateStep("flow-1"), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({
        ord: 0,
        step_type: "send_message",
        config: { template: "Ola!" },
      });
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/automation/flows/flow-1/steps",
      expect.objectContaining({ ord: 0, step_type: "send_message" }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useUpdateStep
// ---------------------------------------------------------------------------

describe("useUpdateStep", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls PATCH /api/automation/steps/:stepId", async () => {
    mockPatch.mockResolvedValue({
      ...STEP_ITEM,
      config: { template: "Atualizado!" },
    });
    const { result } = renderHook(() => useUpdateStep(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({
        stepId: "step-1",
        flowId: "flow-1",
        config: { template: "Atualizado!" },
      });
    });
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/automation/steps/step-1",
      expect.objectContaining({ config: { template: "Atualizado!" } }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useDeleteStep
// ---------------------------------------------------------------------------

describe("useDeleteStep", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls DELETE /api/automation/steps/:stepId", async () => {
    mockDelete.mockResolvedValue({ ok: true, id: "step-1" });
    const { result } = renderHook(() => useDeleteStep(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ stepId: "step-1", flowId: "flow-1" });
    });
    expect(mockDelete).toHaveBeenCalledWith("/api/automation/steps/step-1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useTriggerFlow
// ---------------------------------------------------------------------------

describe("useTriggerFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/automation/flows/:flowId/trigger", async () => {
    mockPost.mockResolvedValue(EXECUTION_ITEM);
    const { result } = renderHook(() => useTriggerFlow(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({
        flowId: "flow-1",
        lead_id: "lead-uuid-123",
      });
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/automation/flows/flow-1/trigger",
      expect.objectContaining({ lead_id: "lead-uuid-123" }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useCancelExecution
// ---------------------------------------------------------------------------

describe("useCancelExecution", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls DELETE /api/automation/executions/:id", async () => {
    mockDelete.mockResolvedValue({ ok: true, id: "exec-1" });
    const { result } = renderHook(() => useCancelExecution(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync("exec-1");
    });
    expect(mockDelete).toHaveBeenCalledWith(
      "/api/automation/executions/exec-1",
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// Tests: useRunDue
// ---------------------------------------------------------------------------

describe("useRunDue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/automation/run-due and returns counts", async () => {
    const result_data = { processed: 5, sent: 3, skipped: 1, failed: 1 };
    mockPost.mockResolvedValue(result_data);
    const { result } = renderHook(() => useRunDue(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(mockPost).toHaveBeenCalledWith("/api/automation/run-due", {});
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(result_data);
  });

  it("surfaces error on failure", async () => {
    mockPost.mockRejectedValue(new Error("Falha ao processar acoes pendentes"));
    const { result } = renderHook(() => useRunDue(), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      try {
        await result.current.mutateAsync();
      } catch {
        // expected
      }
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("pendentes");
  });
});
