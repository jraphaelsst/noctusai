/**
 * useAgents.ts hook tests — contract §E.2 (`GET /api/agents`,
 * `POST /api/agents/{key}/toggle`). Covers the optimistic toggle +
 * rollback on a 502 `upstream_failed`.
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

const JULIA = {
  key: "julia",
  nome: "Julia",
  runtime: "claude_sdk",
  owner_product: null,
  ativo: true,
  estado_externo: null,
  aviso: null,
};

const ONE_CHAT = {
  key: "one-chat",
  nome: "One Chat",
  runtime: "external",
  owner_product: "social-wiring",
  ativo: false,
  estado_externo: { auto_reply_enabled: false },
  aviso: null,
};

beforeEach(() => vi.clearAllMocks());

describe("useAgents", () => {
  it("GETs /api/agents and returns the item list", async () => {
    mockGet.mockResolvedValue({ items: [JULIA, ONE_CHAT], total: 2 });
    const { useAgents } = await import("@/hooks/useAgents");
    const qc = newClient();
    const { result } = renderHook(() => useAgents(), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/agents");
    expect(result.current.data?.map((a) => a.key)).toEqual(["julia", "one-chat"]);
  });
});

describe("useToggleAgent", () => {
  it("POSTs /api/agents/{key}/toggle with {ativo} and reconciles on success", async () => {
    mockGet.mockResolvedValue({ items: [JULIA], total: 1 });
    mockPost.mockResolvedValue({ ...JULIA, ativo: false });
    const { useAgents } = await import("@/hooks/useAgents");
    const { useToggleAgent } = await import("@/hooks/useAgents");
    const qc = newClient();
    const agents = renderHook(() => useAgents(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(agents.result.current.showSkeleton).toBe(false));

    const toggle = renderHook(() => useToggleAgent(), { wrapper: wrapper(qc) });
    await toggle.result.current.mutateAsync({ key: "julia", ativo: false });

    expect(mockPost).toHaveBeenCalledWith("/api/agents/julia/toggle", { ativo: false });
    await waitFor(() => expect(agents.result.current.data?.[0].ativo).toBe(false));
  });

  it("optimistically flips ativo, then rolls back on a 502 upstream_failed", async () => {
    mockGet.mockResolvedValue({ items: [ONE_CHAT], total: 1 });
    const { ApiError } = await import("@/lib/errors");
    // A controllable, not-yet-settled promise — lets the test observe the
    // OPTIMISTIC state (onMutate has run, the request is still in flight)
    // before deciding when the server responds, instead of racing a
    // pre-rejected promise against React's render/commit cycle.
    let rejectRequest!: (err: unknown) => void;
    mockPost.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectRequest = reject;
      }),
    );
    const { useAgents, useToggleAgent } = await import("@/hooks/useAgents");
    const qc = newClient();
    const agents = renderHook(() => useAgents(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(agents.result.current.showSkeleton).toBe(false));
    expect(agents.result.current.data?.[0].ativo).toBe(false);

    const toggle = renderHook(() => useToggleAgent(), { wrapper: wrapper(qc) });
    const attempt = toggle.result.current.mutateAsync({ key: "one-chat", ativo: true });
    // Swallow the eventual rejection here too, so a slow assertion below
    // never leaves an unhandled-rejection warning from this same promise.
    attempt.catch(() => {});

    // Optimistic flip lands via onMutate, before the server has responded.
    await waitFor(() => expect(agents.result.current.data?.[0].ativo).toBe(true));

    rejectRequest(new ApiError(502, "Falha ao comunicar com o social-wiring."));
    await expect(attempt).rejects.toThrow();

    // Rolled back to the pre-toggle state.
    await waitFor(() => expect(agents.result.current.data?.[0].ativo).toBe(false));
  });
});
