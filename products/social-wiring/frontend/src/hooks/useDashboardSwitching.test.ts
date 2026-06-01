/**
 * Wiring test — proves the live account/client switcher actually re-points the
 * YT data hooks (the "build switching now" requirement). The switcher writes
 * `activeAccountId` to the shared useActiveAccountStore; this test asserts that
 * useDashboardStats / useVideos READ it and thread it into the request URL —
 * i.e. selecting an account in-view re-fetches that account's data.
 *
 * This is the wiring leg that route-exists ≠ wired warns about: components that
 * merely accept an accountId prop nobody passes are NOT wired.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useDashboardStats } from "./useDashboard";
import { useVideos } from "./useVideos";
import { useActiveAccountStore } from "@/state/useActiveAccount";

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockResolvedValue([]);
  useActiveAccountStore.setState({ activeAccountId: null, activeClientId: null });
});
afterEach(() => {
  useActiveAccountStore.setState({ activeAccountId: null, activeClientId: null });
});

describe("active-account switching wires into the YT data hooks", () => {
  it("useDashboardStats omits account_id when no account is selected (org default)", async () => {
    renderHook(() => useDashboardStats());
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet.mock.calls[0][0]).toBe("/api/dashboard/stats");
  });

  it("useDashboardStats threads the store's activeAccountId into the request", async () => {
    useActiveAccountStore.setState({ activeAccountId: "acc-123" });
    renderHook(() => useDashboardStats());
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet.mock.calls[0][0]).toContain("account_id=acc-123");
  });

  it("an explicit accountId arg overrides the store", async () => {
    useActiveAccountStore.setState({ activeAccountId: "store-acc" });
    renderHook(() => useDashboardStats("explicit-acc"));
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet.mock.calls[0][0]).toContain("account_id=explicit-acc");
  });

  it("useVideos threads the store's activeAccountId into the request", async () => {
    mockGet.mockResolvedValue({ items: [], next_cursor: null, total: 0 });
    useActiveAccountStore.setState({ activeAccountId: "acc-789" });
    renderHook(() => useVideos());
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet.mock.calls[0][0]).toContain("account_id=acc-789");
  });
});
