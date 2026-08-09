/**
 * useChannelTrend — wiring tests.
 *
 * Verifies that the hook threads accountId from the store into the request URL
 * and re-fetches when the account changes.
 *
 * Uses a direct URL-capture approach: mock api.get to record what URLs are
 * called, then assert on the captured set. We do NOT render via renderHook
 * (avoids the act/asyncEffect timeout pattern seen on other hooks in this suite).
 * Instead we call the hook's internal URL builder via the useCallback path,
 * verified through the captured api.get calls after mount.
 */
import { describe, it, expect, vi, afterEach } from "vitest";

// ─── Seed infra mock ────────────────────────────────────────────────────────
const capturedUrls: string[] = [];

vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: vi.fn((url: string) => {
      capturedUrls.push(url);
      return Promise.resolve({ points: [] });
    }),
    post: vi.fn(() => Promise.resolve({})),
  },
}));

afterEach(async () => {
  capturedUrls.length = 0;
  const { useActiveAccountStore } = await import("@/state/useActiveAccount");
  useActiveAccountStore.setState({ activeAccountIdByProvider: {}, activeMarcaId: null });
  (await import("@testing-library/react")).cleanup();
  vi.clearAllMocks();
});

// ─── Helper: render hook via RTL ─────────────────────────────────────────────

async function mountHook(days = 30) {
  const { renderHook, waitFor } = await import("@testing-library/react");
  const { useChannelTrend } = await import("./useChannelTrend");
  const result = renderHook(() => useChannelTrend(days));
  // Wait for loading to complete so useEffect has fired
  await waitFor(() => {
    expect(result.result.current.loading).toBe(false);
  }, { timeout: 3000 });
  return result;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("useChannelTrend — URL construction", () => {
  it("omits account_id in URL when store is null", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({ activeAccountIdByProvider: {}, activeMarcaId: null });

    await mountHook(30);

    expect(capturedUrls.some((url) => url.includes("account_id"))).toBe(false);
  });

  it("includes days param in URL", async () => {
    await mountHook(90);
    expect(capturedUrls.some((url) => url.includes("days=90"))).toBe(true);
  });

  it("includes account_id in URL when store has an active account", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "acc-test-xyz" },
      activeMarcaId: null,
    });

    await mountHook(30);

    expect(capturedUrls.some((url) => url.includes("account_id=acc-test-xyz"))).toBe(true);
  });
});

describe("useChannelTrend — account switching", () => {
  it("re-fetches with new account_id when store switches", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "acc-first" },
      activeMarcaId: null,
    });

    const { renderHook, waitFor, act } = await import("@testing-library/react");
    const { useChannelTrend } = await import("./useChannelTrend");
    const { rerender, result } = renderHook(() => useChannelTrend(30));

    // Wait for first fetch
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    // Switch account
    await act(async () => {
      useActiveAccountStore.setState({
        activeAccountIdByProvider: { youtube: "acc-second" },
        activeMarcaId: null,
      });
    });

    // Wait for re-fetch
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    const hasFirst = capturedUrls.some((url) => url.includes("account_id=acc-first"));
    const hasSecond = capturedUrls.some((url) => url.includes("account_id=acc-second"));
    expect(hasFirst).toBe(true);
    expect(hasSecond).toBe(true);
  });
});
