/** useOptOuts -- cursor pagination over GET /api/studio/opt-outs, and the resend mutation. Synthetic data. */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost } }));

import { useOptOuts, useReenviarNotificacao } from "@/hooks/useOptOuts";

const wrapper = (qc: QueryClient) => ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: qc }, children);
const novo = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

beforeEach(() => vi.clearAllMocks());

describe("useOptOuts", () => {
  it("pages by cursor and concatenates the pages", async () => {
    mockGet
      .mockResolvedValueOnce({ items: [{ id: "a" }], next_cursor: "c1" })
      .mockResolvedValueOnce({ items: [{ id: "b" }], next_cursor: null });
    const { result } = renderHook(() => useOptOuts(), { wrapper: wrapper(novo()) });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/opt-outs", { limit: 50 });
    expect(result.current.hasMore).toBe(true);
    act(() => result.current.fetchMore());
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(mockGet).toHaveBeenLastCalledWith("/api/studio/opt-outs", { limit: 50, cursor: "c1" });
    expect(result.current.hasMore).toBe(false);
    expect(result.current.showSkeleton).toBe(false);
  });

  it("reports isError on failure", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useOptOuts(), { wrapper: wrapper(novo()) });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useReenviarNotificacao", () => {
  it("POSTs to the notificar route and refreshes the list", async () => {
    mockPost.mockResolvedValue({ id: "e1", notificacao_status: "enviada" });
    const qc = novo();
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useReenviarNotificacao(), { wrapper: wrapper(qc) });
    await act(async () => {
      await result.current.mutateAsync("e1");
    });
    expect(mockPost).toHaveBeenCalledWith("/api/studio/opt-outs/e1/notificar");
    expect(inv).toHaveBeenCalledWith({ queryKey: ["agents", "opt-outs"] });
  });
});
