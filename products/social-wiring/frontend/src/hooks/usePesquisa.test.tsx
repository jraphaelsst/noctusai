/**
 * usePesquisa.test.tsx — query URL building, offset paging ("Carregar mais"),
 * the two-signal loading rule and list+counts invalidation after mutations.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import { api } from "@noctusai/seed/infra";
import { PESQUISA_KEY, useAprovarItem, usePesquisaItens, useZerarPesquisa } from "./usePesquisa";

const get = api.get as ReturnType<typeof vi.fn>;
const post = api.post as ReturnType<typeof vi.fn>;

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const W = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, W };
}

const it1 = (id: string) => ({ id, content: id });
const filters = { marcaId: "m1", status: "approved" as const, variableSlug: "DORES", sort: "plays" as const, pageSize: 2 };

beforeEach(() => vi.clearAllMocks());

describe("usePesquisaItens", () => {
  it("builds the query, exposes showSkeleton then pages by offset", async () => {
    get
      .mockResolvedValueOnce({ success: true, data: { items: [it1("a"), it1("b")], total: 3 } })
      .mockResolvedValueOnce({ success: true, data: { items: [it1("c")], total: 3 } });
    const { W } = wrapper();
    const { result } = renderHook(() => usePesquisaItens(filters), { wrapper: W });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.showSkeleton).toBe(false);
    const url = get.mock.calls[0][0] as string;
    expect(url).toContain("marca_id=m1");
    expect(url).toContain("status=approved");
    expect(url).toContain("variable_slug=DORES");
    expect(url).toContain("sort=plays");
    expect(url).toContain("limit=2");
    expect(url).toContain("offset=0");
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.items).toHaveLength(3));
    expect(get.mock.calls[1][0]).toContain("offset=2");
    expect(result.current.hasNextPage).toBe(false);
  });

  it("does not fetch without a marca", () => {
    const { W } = wrapper();
    const { result } = renderHook(() => usePesquisaItens({ ...filters, marcaId: null }), { wrapper: W });
    expect(get).not.toHaveBeenCalled();
    expect(result.current.showSkeleton).toBe(false);
  });
});

describe("mutations", () => {
  it("approve and empty invalidate the whole pesquisa family (list + counts)", async () => {
    post.mockResolvedValue({ success: true, data: {} });
    const { qc, W } = wrapper();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => ({ ap: useAprovarItem(), ze: useZerarPesquisa() }), { wrapper: W });
    await act(async () => {
      await result.current.ap.mutateAsync("i1");
    });
    expect(post.mock.calls[0][0]).toBe("/api/media-creation/pesquisa/items/i1/approve");
    expect(spy).toHaveBeenCalledWith({ queryKey: PESQUISA_KEY });
    await act(async () => {
      await result.current.ze.mutateAsync("m1");
    });
    expect(post.mock.calls[1]).toEqual([
      "/api/media-creation/pesquisa/items/empty",
      { marca_id: "m1", confirm: true },
    ]);
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
