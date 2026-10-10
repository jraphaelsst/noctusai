/** Headline mutations hit the §4.4 endpoints and invalidate the geracao family. */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import {
  useEditarHeadline,
  useExcluirHeadlines,
  useFavoritarHeadline,
} from "./useHeadlineMutations";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

afterEach(() => {
  vi.restoreAllMocks();
  api.post.mockReset();
  api.patch.mockReset();
});

describe("useHeadlineMutations", () => {
  it("edita via PATCH {texto} e devolve a headline", async () => {
    api.patch.mockResolvedValue({ data: { id: "h1", texto: "novo" } });
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEditarHeadline(), { wrapper });
    const h = await result.current.mutateAsync({ id: "h1", texto: "novo" });
    expect(api.patch).toHaveBeenCalledWith("/api/media-creation/headlines/h1", { texto: "novo" });
    expect(h.texto).toBe("novo");
    await waitFor(() => expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao"] }));
  });

  it("favoritar e desfavoritar usam rotas distintas", async () => {
    api.post.mockResolvedValue({ data: { id: "h1", favorita: true } });
    const { result } = renderHook(() => useFavoritarHeadline(), { wrapper });
    await result.current.mutateAsync({ id: "h1", favoritar: true });
    await result.current.mutateAsync({ id: "h1", favoritar: false });
    expect(api.post.mock.calls.map((c) => c[0])).toEqual([
      "/api/media-creation/headlines/h1/favoritar",
      "/api/media-creation/headlines/h1/desfavoritar",
    ]);
  });

  it("exclui em lote via POST /excluir {ids}", async () => {
    api.post.mockResolvedValue({ data: { excluidos: 2 } });
    const { result } = renderHook(() => useExcluirHeadlines(), { wrapper });
    const r = await result.current.mutateAsync(["a", "b"]);
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/headlines/excluir", { ids: ["a", "b"] });
    expect(r.excluidos).toBe(2);
  });
});
