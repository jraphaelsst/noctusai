/**
 * Tests for useIntegrationAccounts hooks.
 *
 * Verifies:
 *   · queries return data from the API (bare arrays/objects — no envelope)
 *   · mutations call the right endpoints and invalidate query keys
 *   · useStartYouTubeOAuth / useStartProviderOAuth open the auth_url in a
 *     NEW TAB (window.open at mutation start, tab.location.href on success),
 *     falling back to a same-tab redirect when the popup is blocked
 *   · useAdoptLegacy calls adopt-legacy endpoint and invalidates accounts
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

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
  useAdoptLegacy,
  useStartYouTubeOAuth,
  useStartProviderOAuth,
} from "./useIntegrationAccounts";

// Reset mocks between tests to avoid cross-test pollution
beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useIntegrationProviders", () => {
  it("calls GET /api/integrations/providers and returns bare array", async () => {
    // API now returns a BARE array (not {providers: [...]})
    mockGet.mockResolvedValue([{ id: "youtube", display_name: "YouTube" }]);
    const hook = useIntegrationProviders() as any;
    const data = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/integrations/providers");
    expect(data).toHaveLength(1);
    // provider uses `id` (not `name`)
    expect(data[0].id).toBe("youtube");
  });

  it("returns empty array when API returns null/undefined", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useIntegrationProviders() as any;
    const data = await hook._queryFn();
    expect(data).toEqual([]);
  });
});

describe("useIntegrationAccounts", () => {
  it("calls GET /api/integrations/accounts without filter and returns bare array", async () => {
    mockGet.mockResolvedValue([]);
    const hook = useIntegrationAccounts() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/integrations/accounts");
  });

  it("calls GET /api/integrations/accounts?provider=youtube with filter", async () => {
    mockGet.mockResolvedValue([]);
    const hook = useIntegrationAccounts("youtube") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/integrations/accounts?provider=youtube"
    );
  });

  it("returns empty array when API returns null/undefined", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useIntegrationAccounts() as any;
    const data = await hook._queryFn();
    expect(data).toEqual([]);
  });
});

describe("useIntegrationAccount", () => {
  it("calls GET /api/integrations/accounts/:id and returns bare object", async () => {
    // API returns bare account (not {data: {...}})
    mockGet.mockResolvedValue({ id: "abc", provider: "youtube" });
    const hook = useIntegrationAccount("abc") as any;
    const data = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/integrations/accounts/abc");
    expect(data.id).toBe("abc");
  });
});

describe("useCreateAccount", () => {
  it("calls POST and invalidates accounts keys", async () => {
    // API returns bare account
    mockPost.mockResolvedValue({ id: "1", provider: "youtube" });
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
  it("calls PATCH /api/integrations/accounts/:id with bare response", async () => {
    // API returns bare account (not {data: {...}})
    mockPatch.mockResolvedValue({ id: "1", provider: "youtube" });
    const hook = useUpdateAccount() as any;
    await hook.mutateAsync({ id: "1", account_label: "Updated" });
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/integrations/accounts/1",
      expect.objectContaining({ account_label: "Updated" })
    );
    expect(invalidateQueriesMock).toHaveBeenCalled();
  });
});

describe("useSetDefaultAccount", () => {
  it("calls PATCH /api/integrations/accounts/:id/set-default with bare response", async () => {
    // API returns bare account (not {data: {...}})
    mockPatch.mockResolvedValue({ id: "1", provider: "youtube" });
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

describe("useAdoptLegacy", () => {
  it("calls POST /api/integrations/accounts/:provider/adopt-legacy and invalidates", async () => {
    mockPost.mockResolvedValue({ id: "acc-1", provider: "youtube" });
    const hook = useAdoptLegacy("youtube") as any;
    await hook.mutateAsync();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/integrations/accounts/youtube/adopt-legacy",
      {}
    );
    expect(invalidateQueriesMock).toHaveBeenCalled();
  });

  it("handles null response (nothing to adopt)", async () => {
    mockPost.mockResolvedValue(null);
    const hook = useAdoptLegacy("youtube") as any;
    // Should not throw
    const result = await hook.mutateAsync();
    expect(result).toBeNull();
  });
});

describe("useStartYouTubeOAuth", () => {
  it("calls POST /api/integrations/accounts/youtube/oauth/start and opens a new tab", async () => {
    const fakeTab = { location: { href: "" } };
    const openSpy = vi.fn().mockReturnValue(fakeTab);
    const assignSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    Object.defineProperty(window, "location", {
      value: { assign: assignSpy },
      writable: true,
    });
    mockPost.mockResolvedValue({ auth_url: "https://accounts.google.com/o/oauth2/auth?foo=1", state: "abc" });
    const hook = useStartYouTubeOAuth() as any;
    await hook.mutateAsync();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/integrations/accounts/youtube/oauth/start",
      {}
    );
    expect(openSpy).toHaveBeenCalledWith("", "_blank");
    expect(fakeTab.location.href).toBe(
      "https://accounts.google.com/o/oauth2/auth?foo=1"
    );
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("falls back to window.location.assign when the popup is blocked", async () => {
    vi.stubGlobal("open", vi.fn().mockReturnValue(null));
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign: assignSpy },
      writable: true,
    });
    mockPost.mockResolvedValue({ auth_url: "https://accounts.google.com/o/oauth2/auth?foo=2", state: "abc" });
    const hook = useStartYouTubeOAuth() as any;
    await hook.mutateAsync();
    expect(assignSpy).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/auth?foo=2");
  });
});

describe("useStartProviderOAuth", () => {
  it("calls POST /api/integrations/accounts/{provider}/oauth/start and opens a new tab", async () => {
    const fakeTab = { location: { href: "" } };
    const openSpy = vi.fn().mockReturnValue(fakeTab);
    const assignSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    Object.defineProperty(window, "location", {
      value: { assign: assignSpy },
      writable: true,
    });
    mockPost.mockResolvedValue({ auth_url: "https://accounts.google.com/o/oauth2/auth?bar=1", state: "xyz" });
    const hook = useStartProviderOAuth("gmail") as any;
    await hook.mutateAsync();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/integrations/accounts/gmail/oauth/start",
      {}
    );
    expect(openSpy).toHaveBeenCalledWith("", "_blank");
    expect(fakeTab.location.href).toBe(
      "https://accounts.google.com/o/oauth2/auth?bar=1"
    );
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("falls back to window.location.assign when the popup is blocked", async () => {
    vi.stubGlobal("open", vi.fn().mockReturnValue(null));
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign: assignSpy },
      writable: true,
    });
    mockPost.mockResolvedValue({ auth_url: "https://accounts.google.com/o/oauth2/auth?bar=2", state: "xyz" });
    const hook = useStartProviderOAuth("drive") as any;
    await hook.mutateAsync();
    expect(assignSpy).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/auth?bar=2");
  });
});
