/**
 * Tests for useClientes hooks — PROJECT.md §5 (the FE↔BE contract). Mirrors
 * `usePortalRoi.test.ts`'s mocking pattern (mock `@tanstack/react-query`
 * itself so `_queryFn`/`_mutationFn` can be invoked directly, mock
 * `@noctusai/seed/infra`'s `api`).
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

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(
    ({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
      data: undefined,
      isPending: false,
      isFetching: false,
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
      mutate: (
        vars: unknown,
        opts?: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void },
      ) => {
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
  formatCountOrDash,
  useClienteMutations,
  useClientesBoard,
} from "./useClientes";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useClientesBoard", () => {
  it("GETs /api/clientes with no query when filters are absent (server defaults to active-only, D4)", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useClientesBoard() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes");
  });

  it("appends ativo=false only for the inactive tab, never ativo=true for the default tab", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useClientesBoard({ ativo: false, page: 2, page_size: 24 }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes?page=2&page_size=24&ativo=false");
  });

  it("appends q and corretor_id when given", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useClientesBoard({ q: "maria", corretor_id: "c1" }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes?q=maria&corretor_id=c1");
  });

  it("falls back to an empty page on a bare-null response, never undefined", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useClientesBoard() as any;
    const result = await hook._queryFn();
    expect(result).toEqual({ items: [], total: 0, page: 1, pages: 1 });
  });
});

describe("useClienteMutations", () => {
  it("PATCHes /api/clientes/{id} with { ativo: true } to restore (D4)", async () => {
    mockPatch.mockResolvedValue({ id: "cl1", ativo: true });
    const { update } = useClienteMutations();
    await (update as any).mutateAsync({ id: "cl1", body: { ativo: true } });
    expect(mockPatch).toHaveBeenCalledWith("/api/clientes/cl1", { ativo: true });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["sw", "clientes"] });
  });
});

describe("formatCountOrDash", () => {
  it("renders null/undefined as a dash, never a lying zero", () => {
    expect(formatCountOrDash(null)).toBe("—");
    expect(formatCountOrDash(undefined)).toBe("—");
  });

  it("renders a real zero as 0, not a dash", () => {
    expect(formatCountOrDash(0)).toBe("0");
  });

  it("renders pt-BR thousands separators", () => {
    expect(formatCountOrDash(14483)).toBe("14.483");
  });
});
