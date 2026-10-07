/**
 * Real-QueryClient test for `useClienteMutations().remove`: the deleted id's
 * own queries must not be refetched (the "[404] Cliente não encontrado"
 * toast storm), while the board/funil still refresh.
 */
import { describe, expect, it, vi } from "vitest";

const { mockDelete } = vi.hoisted(() => ({ mockDelete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: mockDelete },
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { useClienteMutations } from "./useClientes";

describe("useClienteMutations().remove", () => {
  it("invalidates the board + funil, never refetches the deleted id, then drops its cache", async () => {
    mockDelete.mockResolvedValue({ deleted: true, storage_falhas: [] });
    const qc = new QueryClient();
    const fetchBoard = vi.fn().mockResolvedValue([]);
    const fetchCard = vi.fn().mockResolvedValue({});
    const fetchOther = vi.fn().mockResolvedValue({});
    const fetchFunil = vi.fn().mockResolvedValue([]);
    // Mount observers so the queries are ACTIVE, as in the open dialog/page.
    const { QueryObserver } = await import("@tanstack/react-query");
    const obs = [
      new QueryObserver(qc, { queryKey: ["sw", "clientes", "board", {}], queryFn: fetchBoard }),
      new QueryObserver(qc, { queryKey: ["sw", "cardHub", "c1", "card"], queryFn: fetchCard }),
      new QueryObserver(qc, { queryKey: ["sw", "pessoa", "c1", "resumo"], queryFn: fetchCard }),
      new QueryObserver(qc, { queryKey: ["sw", "cardHub", "c2", "card"], queryFn: fetchOther }),
      new QueryObserver(qc, { queryKey: ["sw-funil"], queryFn: fetchFunil }),
    ];
    const unsub = obs.map((o) => o.subscribe(() => {}));
    await waitFor(() => expect(fetchFunil).toHaveBeenCalledTimes(1));
    fetchBoard.mockClear();
    fetchCard.mockClear();
    fetchFunil.mockClear();

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useClienteMutations(), { wrapper });
    await act(async () => {
      await result.current.remove.mutateAsync("c1");
    });

    await waitFor(() => expect(fetchBoard).toHaveBeenCalledTimes(1));
    expect(fetchFunil).toHaveBeenCalledTimes(1);
    expect(fetchCard).not.toHaveBeenCalled();
    await waitFor(() => expect(qc.getQueryCache().find({ queryKey: ["sw", "cardHub", "c1", "card"] })).toBeUndefined());
    expect(qc.getQueryCache().find({ queryKey: ["sw", "cardHub", "c2", "card"] })).toBeDefined();
    unsub.forEach((u) => u());
  });
});
