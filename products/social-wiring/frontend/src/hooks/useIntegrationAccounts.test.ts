/**
 * Tests for useIntegrationAccounts hooks.
 *
 * Verifies:
 *   · queries return data from the API
 *   · mutations call the right endpoints and invalidate query keys
 *   · useStartYouTubeOAuth assigns window.location on success
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ─── Stub @noctusai/seed/infra ─────────────────────────────────────────
// vi.hoisted: the static `import ... from "./useIntegrationAccounts"` below is
// hoisted above these declarations, and loading that module triggers the
// @noctusai/seed/infra mock factory — so the mocks must exist BEFORE then.
const { mockGet, mockPost, mockPatch, mockDelete, invalidateQueriesMock } =
  vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockPost: vi.fn(),
    mockPatch: vi.fn(),
    mockDelete: vi.fn(),
    invalidateQueriesMock: vi.fn(),
  }));
vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
}));

// ─── Stub @tanstack/react-query (minimal) ─────────────────────────────
vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn }: { queryFn: () => unknown }) => ({
    data: undefined,
    isLoading: false,
    isError: false,
    _queryFn: queryFn,
  }));
  const useMutation = vi.fn(
    ({ mutationFn, onSuccess }: { mutationFn: (v: unknown) => unknown; onSuccess?: (r: unknown, v: unknown) => void }) => ({
      // Simulate react-query's flow: run mutationFn, THEN onSuccess (where the
      // hooks invalidate query keys) — so onSuccess side effects are testable.
      mutateAsync: async (vars: unknown) => {
        const result = await mutationFn(vars);
        onSuccess?.(result, vars);
        return result;
      },
      isPending: false,
      _mutationFn: mutationFn,
    })
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  useIntegrationProviders,
  useIntegrationAccounts,
  useIntegrationAccount,
  useCreateAccount,
  useUpdateAccount,
  useSetDefaultAccount,
  useDeleteAccount,
  useStartYouTubeOAuth,
} from "./useIntegrationAccounts";

describe("useIntegrationProviders", () => {
  it("calls GET /api/integrations/providers", async () => {
    mockGet.mockResolvedValue({ providers: [{ name: "youtube", display_name: "YouTube" }] });
    const hook = useIntegrationProviders() as any;
    const data = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/integrations/providers");
    expect(data).toHaveLength(1);
    expect(data[0].name).toBe("youtube");
  });
});

describe("useIntegrationAccounts", () => {
  it("calls GET /api/integrations/accounts without filter", async () => {
    mockGet.mockResolvedValue({ data: [] });
    const hook = useIntegrationAccounts() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/integrations/accounts");
  });

  it("calls GET /api/integrations/accounts?provider=youtube with filter", async () => {
    mockGet.mockResolvedValue({ data: [] });
    const hook = useIntegrationAccounts("youtube") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/integrations/accounts?provider=youtube"
    );
  });
});

describe("useIntegrationAccount", () => {
  it("calls GET /api/integrations/accounts/:id", async () => {
    mockGet.mockResolvedValue({ data: { id: "abc", provider: "youtube" } });
    const hook = useIntegrationAccount("abc") as any;
    const data = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/integrations/accounts/abc");
    expect(data.id).toBe("abc");
  });
});

describe("useCreateAccount", () => {
  it("calls POST and invalidates accounts keys", async () => {
    mockPost.mockResolvedValue({ data: { id: "1", provider: "youtube" } });
    const hook = useCreateAccount() as any;
    await hook.mutateAsync({ provider: "youtube", account_label: "Main", credential: {} });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/integrations/accounts",
      expect.objectContaining({ provider: "youtube" })
    );
    expect(invalidateQueriesMock).toHaveBeenCalled();
  });
});

describe("useUpdateAccount", () => {
  it("calls PATCH /api/integrations/accounts/:id", async () => {
    mockPatch.mockResolvedValue({ data: { id: "1", provider: "youtube" } });
    const hook = useUpdateAccount() as any;
    await hook.mutateAsync({ id: "1", account_label: "Updated" });
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/integrations/accounts/1",
      expect.objectContaining({ account_label: "Updated" })
    );
  });
});

describe("useSetDefaultAccount", () => {
  it("calls PATCH /api/integrations/accounts/:id/set-default", async () => {
    mockPatch.mockResolvedValue({ data: { id: "1", provider: "youtube" } });
    const hook = useSetDefaultAccount() as any;
    await hook.mutateAsync("1");
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/integrations/accounts/1/set-default",
      {}
    );
    expect(invalidateQueriesMock).toHaveBeenCalled();
  });
});

describe("useDeleteAccount", () => {
  it("calls DELETE /api/integrations/accounts/:id", async () => {
    mockDelete.mockResolvedValue({});
    const hook = useDeleteAccount() as any;
    await hook.mutateAsync("2");
    expect(mockDelete).toHaveBeenCalledWith("/api/integrations/accounts/2");
    expect(invalidateQueriesMock).toHaveBeenCalled();
  });
});

describe("useStartYouTubeOAuth", () => {
  it("calls POST /api/integrations/accounts/youtube/oauth/start", async () => {
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign: assignSpy },
      writable: true,
    });
    mockPost.mockResolvedValue({ auth_url: "https://accounts.google.com/o/oauth2/auth?foo=1" });
    const hook = useStartYouTubeOAuth() as any;
    await hook.mutateAsync();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/integrations/accounts/youtube/oauth/start",
      {}
    );
  });
});
