/**
 * Cache writes — the screen agrees with the server while the request is still in flight
 * (optimistic) or the moment it answers (commit), never only after the settle refetch.
 * Real QueryClient, deferred API promises. KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { GERACAO_KEY, useFavoritarHeadline } from "./geracao/useHeadlineMutations";
import { useDeleteTestemunha, useCreateTestemunha } from "./useTestemunhas";
import { useInteresseMutations, interessesKey } from "./useInteresses";
import { useAdicionarAlias } from "./useCondominios";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

let qc: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  Object.values(api).forEach((m) => m.mockReset());
});

describe("social-wiring cache writes", () => {
  it("favoritar draws the flag on the cached headline list before the server answers", async () => {
    const key = [...GERACAO_KEY, "headlines", "m1", "lista", "favoritas", "", "", 0];
    qc.setQueryData(key, { items: [{ id: "h1", texto: "x", favorita: false }], total: 1 });
    const d = deferred<unknown>();
    api.post.mockReturnValue(d.promise);
    const { result } = renderHook(() => useFavoritarHeadline(), { wrapper });
    act(() => result.current.mutate({ id: "h1", favoritar: true }));
    await waitFor(() => expect((qc.getQueryData(key) as any).items[0].favorita).toBe(true));
    d.resolve({ data: { id: "h1", texto: "x", favorita: true } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("excluir testemunha removes the row (and one from the total) while the DELETE is pending", async () => {
    const key = ["sw", "settings", "testemunhas"];
    qc.setQueryData(key, { items: [{ id: "a" }, { id: "b" }], total: 2 });
    const d = deferred<unknown>();
    api.delete.mockReturnValue(d.promise);
    const { result } = renderHook(() => useDeleteTestemunha(), { wrapper });
    act(() => result.current.mutate("a"));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [{ id: "b" }], total: 1 }));
    d.resolve(undefined);
  });

  it("criar testemunha puts the server row into the list the moment the POST answers", async () => {
    const key = ["sw", "settings", "testemunhas"];
    qc.setQueryData(key, { items: [{ id: "a" }], total: 1 });
    api.post.mockResolvedValue({ id: "n", nome: "Nova" });
    const { result } = renderHook(() => useCreateTestemunha(), { wrapper });
    await act(() => result.current.mutateAsync({ nome: "Nova", cpf: "1" }));
    expect(qc.getQueryData(key)).toEqual({ items: [{ id: "a" }, { id: "n", nome: "Nova" }], total: 2 });
  });

  it("adicionar interesse commits the row and bumps the total", async () => {
    qc.setQueryData(interessesKey("c1"), { items: [{ id: "i1" }], total: 1 });
    api.post.mockResolvedValue({ id: "i2" });
    const { result } = renderHook(() => useInteresseMutations("c1"), { wrapper });
    await act(() => result.current.add.mutateAsync({} as never));
    expect(qc.getQueryData(interessesKey("c1"))).toEqual({ items: [{ id: "i1" }, { id: "i2" }], total: 2 });
  });

  it("adicionar alias lands in the condomínio detail", async () => {
    const key = ["sw", "condominios", "detalhe", "k1"];
    qc.setQueryData(key, { id: "k1", aliases: [{ id: "a1" }], eventos: [] });
    api.post.mockResolvedValue({ id: "a2", alias: "novo" });
    const { result } = renderHook(() => useAdicionarAlias(), { wrapper });
    await act(() => result.current.mutateAsync({ id: "k1", alias: "novo" }));
    expect((qc.getQueryData(key) as any).aliases.map((a: any) => a.id)).toEqual(["a1", "a2"]);
  });
});
