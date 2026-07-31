/**
 * Tests for useN8nWorkflows hooks.
 *
 * Verifies:
 *   · getApiErrorStatus recovers the 424/502/409/422 distinction the brief
 *     calls load-bearing, from the seed api client's Error("[<status>] ...")
 *     convention.
 *   · useN8nWorkflows builds the GET URL with account_id/scope/include_archived.
 *   · assign / unassign hit the exact endpoints + bodies the contract names.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockPatch, mockDelete, invalidateQueriesMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete },
}));

const mockActiveAccountId = vi.hoisted(() => ({ current: "acc-123" as string | null }));
// Provider-aware fake, mirroring the real store: the selection is keyed by
// provider, so asking for anything other than "n8n" yields null. A hook that
// regressed to reading another provider's slot would read null here rather
// than silently picking up this test's id.
vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountId: (provider: string) =>
    provider === "n8n" ? mockActiveAccountId.current : null,
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(
    ({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      _queryFn: queryFn,
      _enabled: enabled,
    }),
  );
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown, v: unknown) => void;
    }) => ({
      mutateAsync: async (vars: unknown) => {
        const result = await mutationFn(vars);
        onSuccess?.(result, vars);
        return result;
      },
      mutate: (vars: unknown, opts?: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }) => {
        Promise.resolve(mutationFn(vars))
          .then((result) => {
            onSuccess?.(result, vars);
            opts?.onSuccess?.(result);
          })
          .catch((err) => opts?.onError?.(err));
      },
      isPending: false,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  getApiErrorStatus,
  useN8nWorkflows,
  useAssignWorkflow,
  useUnassignWorkflow,
} from "./useN8nWorkflows";

beforeEach(() => {
  vi.clearAllMocks();
  mockActiveAccountId.current = "acc-123";
});

describe("getApiErrorStatus", () => {
  it("recovers 424 (reconectar) from the seed api client error shape", () => {
    expect(getApiErrorStatus(new Error("[424] Credencial ausente"))).toBe(424);
  });

  it("recovers 502 (instância indisponível), distinct from 424", () => {
    expect(getApiErrorStatus(new Error("[502] Bad Gateway"))).toBe(502);
  });

  it("recovers 409 (run blocked) and 422 (invalid tree op)", () => {
    expect(getApiErrorStatus(new Error("[409] Fluxo bloqueado"))).toBe(409);
    expect(getApiErrorStatus(new Error("[422] Ciclo inválido"))).toBe(422);
  });

  it("returns null for a non-Error or unshaped error", () => {
    expect(getApiErrorStatus("plain string")).toBeNull();
    expect(getApiErrorStatus(new Error("Servidor indisponivel (/api/n8n/workflows)"))).toBeNull();
  });
});

describe("useN8nWorkflows", () => {
  it("builds GET /api/n8n/workflows with account_id, scope, include_archived", async () => {
    mockGet.mockResolvedValue({ workflows: [], folders: [] });
    const hook = useN8nWorkflows({ scope: "client", includeArchived: true }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/n8n/workflows?account_id=acc-123&scope=client&include_archived=true",
    );
  });

  it("defaults include_archived to false and respects scope=unassigned", async () => {
    mockGet.mockResolvedValue({ workflows: [], folders: [] });
    const hook = useN8nWorkflows({ scope: "unassigned" }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/n8n/workflows?account_id=acc-123&scope=unassigned&include_archived=false",
    );
  });

  it("never returns undefined from queryFn even on a bare-null response", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useN8nWorkflows({ scope: "client" }) as any;
    const result = await hook._queryFn();
    expect(result).toEqual({ workflows: [], folders: [] });
  });
});

describe("useAssignWorkflow / useUnassignWorkflow", () => {
  it("POSTs /api/n8n/workflows/{id}/assign with account_id", async () => {
    mockPost.mockResolvedValue({ id: "wf-1" });
    const hook = useAssignWorkflow() as any;
    await hook.mutateAsync({ workflowId: "wf-1" });
    expect(mockPost).toHaveBeenCalledWith("/api/n8n/workflows/wf-1/assign", {
      account_id: "acc-123",
    });
  });

  it("DELETEs /api/n8n/workflows/{id}/assign?account_id=", async () => {
    mockDelete.mockResolvedValue({ id: "wf-1" });
    const hook = useUnassignWorkflow() as any;
    await hook.mutateAsync({ workflowId: "wf-1" });
    expect(mockDelete).toHaveBeenCalledWith("/api/n8n/workflows/wf-1/assign?account_id=acc-123");
  });
});
