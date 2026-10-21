/**
 * Cache writes (wave 2 of the invalidate-only fan-out) for the storefront hosts: the list
 * shows the change while the request is in flight / the moment it answers.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost, delete: mockDelete } }));

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const w = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
}

beforeEach(() => {
  vi.resetAllMocks();
  mockGet.mockReturnValue(new Promise(() => {})); // the settle refetch must never be what the test relies on
});

describe("storefront host cache writes", () => {
  it("a removed host leaves the list on the click", async () => {
    const { qc, w } = setup();
    const { hostsKey, useStorefrontHostMutations } = await import("@/hooks/useStorefrontHosts");
    qc.setQueryData(hostsKey, [{ hostname: "a.com" }, { hostname: "b.com" }]);
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useStorefrontHostMutations(), { wrapper: w });
    result.current.remove.mutate("a.com");
    await waitFor(() => expect(qc.getQueryData(hostsKey)).toEqual([{ hostname: "b.com" }]));
  });

  it("an added host is in the list the moment the POST answers", async () => {
    const { qc, w } = setup();
    const { hostsKey, useStorefrontHostMutations } = await import("@/hooks/useStorefrontHosts");
    qc.setQueryData(hostsKey, [{ hostname: "a.com" }]);
    mockPost.mockResolvedValue({ data: { hostname: "b.com", org_id: "o", is_primary: false } });
    const { result } = renderHook(() => useStorefrontHostMutations(), { wrapper: w });
    result.current.add.mutate({ hostname: "b.com", is_primary: false });
    await waitFor(() => expect(result.current.add.isSuccess).toBe(true));
    expect((qc.getQueryData(hostsKey) as { hostname: string }[]).map((h) => h.hostname)).toEqual(["a.com", "b.com"]);
  });

  it("re-adding an existing hostname replaces its row (no duplicate)", async () => {
    const { qc, w } = setup();
    const { hostsKey, useStorefrontHostMutations } = await import("@/hooks/useStorefrontHosts");
    qc.setQueryData(hostsKey, [{ hostname: "a.com", is_primary: false }, { hostname: "b.com", is_primary: false }]);
    mockPost.mockResolvedValue({ data: { hostname: "a.com", is_primary: true } });
    const { result } = renderHook(() => useStorefrontHostMutations(), { wrapper: w });
    result.current.add.mutate({ hostname: "a.com", is_primary: true });
    await waitFor(() => expect(result.current.add.isSuccess).toBe(true));
    expect(qc.getQueryData(hostsKey)).toEqual([{ hostname: "a.com", is_primary: true }, { hostname: "b.com", is_primary: false }]);
  });
});
