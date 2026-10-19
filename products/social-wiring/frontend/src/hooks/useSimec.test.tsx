/**
 * useSimec — endpoint paths, loading signals (never isLoading), the
 * `{readout: null}` latest shape, and the config/readout writes.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import {
  simecKeys,
  useComputeSimecReadout,
  useSaveSimecConfig,
  useSimecAccounts,
  useSimecConfig,
  useSimecLatestReadout,
} from "./useSimec";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

afterEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.put.mockReset();
});

describe("useSimec reads", () => {
  it("accounts: skeleton only before first data, then data with no skeleton", async () => {
    let resolve!: (v: unknown) => void;
    api.get.mockReturnValue(new Promise((r) => (resolve = r)));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSimecAccounts(), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);
    await act(async () => resolve({ metrics_source: "instagram_snapshots", accounts: [] }));
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/api/simec/accounts");
  });

  it("config: org-effective without account_id, profile-effective with it", async () => {
    api.get.mockResolvedValue({ version: "v" });
    const { wrapper } = setup();
    renderHook(() => useSimecConfig(null), { wrapper });
    renderHook(() => useSimecConfig("acc-1"), { wrapper });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(api.get).toHaveBeenCalledWith("/api/simec/config?platform=instagram");
    expect(api.get).toHaveBeenCalledWith("/api/simec/config?platform=instagram&account_id=acc-1");
  });

  it("config keeps the previous config painted on a profile switch (placeholderData)", async () => {
    api.get.mockResolvedValueOnce({ version: "A" });
    const { wrapper } = setup();
    const { result, rerender } = renderHook(({ id }) => useSimecConfig(id), {
      wrapper,
      initialProps: { id: "a" as string | null },
    });
    await waitFor(() => expect(result.current.data?.version).toBe("A"));
    api.get.mockReturnValueOnce(new Promise(() => {}));
    rerender({ id: "b" });
    expect(result.current.data?.version).toBe("A");
    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.showSkeleton).toBe(false);
  });

  it("latest readout: {readout: null} is data, not an error; disabled without an account", async () => {
    api.get.mockResolvedValue({ readout: null });
    const { wrapper } = setup();
    const idle = renderHook(() => useSimecLatestReadout(null), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
    expect(idle.result.current.data).toBeUndefined();
    const { result } = renderHook(() => useSimecLatestReadout("acc-1"), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual({ readout: null }));
    expect(api.get).toHaveBeenCalledWith("/api/simec/accounts/acc-1/readouts/latest");
  });
});

describe("useSimec writes", () => {
  it("compute POSTs and becomes the latest readout", async () => {
    const readout = { id: "r1", account_id: "acc-1" };
    api.post.mockResolvedValue(readout);
    api.get.mockResolvedValue({ metrics_source: "fake", accounts: [] });
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useComputeSimecReadout("acc-1"), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ cadence: "semanal" });
    });
    expect(api.post).toHaveBeenCalledWith("/api/simec/accounts/acc-1/readouts", { cadence: "semanal" });
    expect(qc.getQueryData(simecKeys.latest("acc-1"))).toEqual({ readout });
  });

  it("save PUTs the whole org layer, or the profile layer for an account", async () => {
    api.put.mockResolvedValue({ version: "x", layers: {} });
    const { wrapper } = setup();
    const { result } = renderHook(() => useSaveSimecConfig(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ accountId: null, overrides: { baseline: { min_posts: 8 } } });
    });
    expect(api.put).toHaveBeenLastCalledWith("/api/simec/config/org", {
      platform: "instagram",
      overrides: { baseline: { min_posts: 8 } },
    });
    await act(async () => {
      await result.current.mutateAsync({ accountId: "acc-1", overrides: {} });
    });
    expect(api.put).toHaveBeenLastCalledWith("/api/simec/accounts/acc-1/config", {
      platform: "instagram",
      overrides: {},
    });
  });
});
