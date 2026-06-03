/**
 * useClients hook tests.
 *
 * Stubs @/lib/api so no real HTTP is made.
 * Verifies: list query hits /api/clients, createClient posts correctly,
 * archiveClient posts to /archive, updateClient patches.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe("useClients", () => {
  beforeEach(() => vi.clearAllMocks());

  it("queries /api/clients and returns items", async () => {
    const items = [
      {
        id: "c1",
        org_id: "o1",
        name: "Acme Corp",
        email: null,
        phone: null,
        company: "Acme",
        monthly_value: 1500,
        due_date: 10,
        active: true,
        default_billing_type: null,
        billing_automation_enabled: false,
        report_token: null,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
    ];
    mockGet.mockResolvedValue({ items, total: 1, page: 1, page_size: 50 });

    const { useClients } = await import("@/hooks/useClients");
    const { result } = renderHook(() => useClients(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/clients", expect.objectContaining({ active_only: true }));
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].name).toBe("Acme Corp");
  });

  it("createClient posts to /api/clients", async () => {
    mockPost.mockResolvedValue({
      id: "c2",
      org_id: "o1",
      name: "Beta SA",
      active: true,
      billing_automation_enabled: false,
      created_at: "2024-01-02T00:00:00Z",
      updated_at: "2024-01-02T00:00:00Z",
    });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { useCreateClient } = await import("@/hooks/useClients");
    const { result } = renderHook(() => useCreateClient(), { wrapper: wrapper() });

    result.current.mutate({ name: "Beta SA" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/clients", { name: "Beta SA" });
  });

  it("archiveClient posts to /api/clients/{id}/archive", async () => {
    mockPost.mockResolvedValue({ ok: true, id: "c1" });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { useArchiveClient } = await import("@/hooks/useClients");
    const { result } = renderHook(() => useArchiveClient(), { wrapper: wrapper() });

    result.current.mutate("c1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/clients/c1/archive", {});
  });

  it("updateClient patches /api/clients/{id}", async () => {
    mockPatch.mockResolvedValue({
      id: "c1",
      org_id: "o1",
      name: "Acme Updated",
      active: true,
      billing_automation_enabled: false,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-02T00:00:00Z",
    });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { useUpdateClient } = await import("@/hooks/useClients");
    const { result } = renderHook(() => useUpdateClient(), { wrapper: wrapper() });

    result.current.mutate({ id: "c1", data: { name: "Acme Updated" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith("/api/clients/c1", { name: "Acme Updated" });
  });
});
