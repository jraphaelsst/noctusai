/**
 * useCredentials / useAgentSettings hook tests — the platform-admin API
 * (`/api/admin/credentials`, `/api/admin/agent-settings`).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: mockPut, patch: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

const ACADEMIA = {
  name: "academia_api_token",
  label: "Token da API academia-de-reciclagem",
  kind: "product_token",
  env_var: "ACADEMIA_API_TOKEN",
  configured: true,
  source: "env",
  prefix: "pk_aaaaaaaa",
  fingerprint: null,
  value: null,
  expires_at: "2026-10-01T00:00:00Z",
  days_left: 15,
  last_used_at: null,
  revoked: false,
  scopes: ["academia:read"],
  renewable: true,
  probeable: true,
  writable: true,
  ring: [],
  warnings: ["Expira em 15 dia(s) — renove."],
  severity: "warning",
};

beforeEach(() => vi.clearAllMocks());

describe("useCredentials", () => {
  it("GETs the admin list and exposes the two loading signals", async () => {
    mockGet.mockResolvedValue({ items: [ACADEMIA], total: 1, alerts: 1 });
    const { useCredentials } = await import("@/hooks/useCredentials");
    const { result } = renderHook(() => useCredentials(), { wrapper: wrapper(newClient()) });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/admin/credentials");
    expect(result.current.data?.alerts).toBe(1);
  });

  it("does not ask when disabled", async () => {
    const { useCredentials } = await import("@/hooks/useCredentials");
    const { result } = renderHook(() => useCredentials({ enabled: false }), { wrapper: wrapper(newClient()) });
    expect(result.current.showSkeleton).toBe(false);
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("credential mutations", () => {
  it("renew POSTs and replaces the cached row", async () => {
    mockGet.mockResolvedValue({ items: [ACADEMIA], total: 1, alerts: 1 });
    const renewed = { ...ACADEMIA, source: "db", days_left: 90, warnings: [], severity: "info" };
    mockPost.mockResolvedValue({ credential: renewed, warnings: [] });
    const { useCredentials, useRenewCredential } = await import("@/hooks/useCredentials");
    const qc = newClient();
    const list = renderHook(() => useCredentials(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.result.current.data).toBeTruthy());

    const { result } = renderHook(() => useRenewCredential(), { wrapper: wrapper(qc) });
    result.current.mutate({ name: "academia_api_token" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/admin/credentials/academia_api_token/renew", {});
    await waitFor(() => expect(list.result.current.data?.alerts).toBe(0));
    expect(list.result.current.data?.items[0].days_left).toBe(90);
  });

  it("set PUTs the write-only value", async () => {
    mockPut.mockResolvedValue({ ...ACADEMIA, name: "anthropic_api_key" });
    const { useSetCredential } = await import("@/hooks/useCredentials");
    const { result } = renderHook(() => useSetCredential(), { wrapper: wrapper(newClient()) });
    result.current.mutate({ name: "anthropic_api_key", value: "sk-ant-x" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith("/api/admin/credentials/anthropic_api_key", { value: "sk-ant-x" });
  });

  it("ring actions POST to rotate / prune", async () => {
    mockPost.mockResolvedValue({ ...ACADEMIA, name: "approval_assertion_secrets" });
    const { useRingAction } = await import("@/hooks/useCredentials");
    const { result } = renderHook(() => useRingAction(), { wrapper: wrapper(newClient()) });
    result.current.mutate({ action: "rotate" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/admin/credentials/approval_assertion_secrets/rotate", {});
  });
});

describe("useAgentSettings", () => {
  it("GETs and PUTs the runtime settings", async () => {
    const items = [{ key: "max_turns", value: 40, default: 40, source: "env", editable: true, min: 1, max: 200 }];
    mockGet.mockResolvedValue({ items });
    mockPut.mockResolvedValue({ items: [{ ...items[0], value: 12, source: "db" }] });
    const { useAgentSettings, useUpdateAgentSettings } = await import("@/hooks/useAgentSettings");
    const qc = newClient();
    const view = renderHook(() => useAgentSettings(), { wrapper: wrapper(qc) });
    await waitFor(() => expect(view.result.current.data?.[0].value).toBe(40));

    const { result } = renderHook(() => useUpdateAgentSettings(), { wrapper: wrapper(qc) });
    result.current.mutate({ max_turns: 12 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith("/api/admin/agent-settings", { max_turns: 12 });
    await waitFor(() => expect(view.result.current.data?.[0].value).toBe(12));
  });
});
