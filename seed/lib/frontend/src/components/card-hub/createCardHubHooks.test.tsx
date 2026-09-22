/**
 * Tests for `createCardHubHooks` — the card hub's data layer.
 *
 * Pins the properties Slice F depends on to swap social-wiring's
 * `useCardHub.ts` onto this factory with zero behaviour change:
 *  - query keys derived from `rootKey` are BYTE-IDENTICAL to SW's
 *    (`["sw","cardHub", id, "card"]`, `[..., "timeline", kinds ?? "all"]`, …);
 *  - paths are SW's (`/api/clientes/{id}/card`, `/api/clientes/tags`, …);
 *  - optimistic writes roll back to the snapshot on failure;
 *  - invalidation stays narrow (a checklist tick never refetches documentos),
 *    plus the product-declared `documentoInvalidates` sub-keys;
 *  - multipart goes through `api.upload`, never `post`.
 *
 * The api is an injected test double (the factory's DI seam) — no module is
 * mocked.
 */
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

import { cardHubLoadingState, createCardHubHooks, flattenTimeline, type CardHubApi } from "./createCardHubHooks";
import type { CardResumoBase, Checklist, Tag, TimelinePage } from "./types";

let api: { [K in keyof CardHubApi]: ReturnType<typeof vi.fn> };
let queryClient: QueryClient;

function makeHooks() {
  return createCardHubHooks(
    {
      rootKey: ["sw", "cardHub"],
      basePath: "/api/clientes",
      entityLabel: "cliente",
      documentoInvalidates: ["documento-checklist"],
    },
    api as unknown as CardHubApi,
  );
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const resumo = (tags: Tag[] = []): CardResumoBase => ({
  tags,
  membros: [],
  descricao: null,
  datas: {
    data_inicio: null,
    data_entrega: null,
    entrega_concluida: false,
    lembrete_minutos_antes: null,
    recorrencia: null,
  },
  badges: {
    notas: 0,
    documentos: 0,
    touches: 0,
    checklist_total: 0,
    checklist_concluidos: 0,
    tem_descricao: false,
    temperatura: null,
  },
});

beforeEach(() => {
  api = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
  };
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  cleanup();
  queryClient.clear();
});

describe("createCardHubHooks — query keys are SW's, byte for byte", () => {
  it("🔴 derives every key from rootKey in SW's exact shape", () => {
    const { keys } = makeHooks();
    expect(keys.root).toEqual(["sw", "cardHub"]);
    expect(keys.card("c1")).toEqual(["sw", "cardHub", "c1", "card"]);
    expect(keys.timeline("c1")).toEqual(["sw", "cardHub", "c1", "timeline", "all"]);
    expect(keys.timeline("c1", ["nota"])).toEqual(["sw", "cardHub", "c1", "timeline", ["nota"]]);
    expect(keys.membros("c1")).toEqual(["sw", "cardHub", "c1", "membros"]);
    expect(keys.checklists("c1")).toEqual(["sw", "cardHub", "c1", "checklists"]);
    expect(keys.checklistExtras("c1")).toEqual(["sw", "cardHub", "c1", "checklist-extras"]);
    expect(keys.documentos("c1")).toEqual(["sw", "cardHub", "c1", "documentos"]);
    expect(keys.acessos("c1", "d1")).toEqual(["sw", "cardHub", "c1", "documentos", "d1", "acessos"]);
    expect(keys.tags).toEqual(["sw", "cardHub", "tags"]);
    expect(keys.tiposDocumento).toEqual(["sw", "cardHub", "tiposDocumento"]);
  });
});

describe("createCardHubHooks — reads", () => {
  it("fetches the card summary from `${basePath}/{id}/card`, disabled without an id", async () => {
    const hooks = makeHooks();
    api.get.mockResolvedValue(resumo());
    const { result } = renderHook(() => hooks.useCardResumo("c 1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.get).toHaveBeenCalledWith("/api/clientes/c%201/card");

    api.get.mockClear();
    renderHook(() => hooks.useCardResumo(null), { wrapper });
    expect(api.get).not.toHaveBeenCalled();
  });

  it("paginates the timeline by cursor with SW's params, and flattens pages", async () => {
    const hooks = makeHooks();
    const p1: TimelinePage = {
      items: [{ id: "e1", kind: "nota", ocorrido_em: "x", ator: null } as never],
      total: 2,
      next_cursor: "CUR",
    };
    const p2: TimelinePage = {
      items: [{ id: "e2", kind: "documento", ocorrido_em: "x", ator: null } as never],
      total: 2,
      next_cursor: null,
    };
    api.get.mockResolvedValueOnce(p1).mockResolvedValueOnce(p2);
    const { result } = renderHook(() => hooks.useTimeline("c1", ["nota", "documento"]), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.get).toHaveBeenLastCalledWith(
      "/api/clientes/c1/timeline?limit=50&kinds=nota%2Cdocumento",
    );
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2));
    expect(result.current.hasNextPage).toBe(false);
    expect(api.get).toHaveBeenLastCalledWith(
      "/api/clientes/c1/timeline?limit=50&cursor=CUR&kinds=nota%2Cdocumento",
    );
    expect(flattenTimeline(result.current.data?.pages).map((e) => e.id)).toEqual(["e1", "e2"]);
  });

  it("reads the org tag catalogue and the tipos from the collection path", async () => {
    const hooks = makeHooks();
    api.get.mockResolvedValue({ items: [{ id: "t1", nome: "A", cor: "#000" }], total: 1 });
    const tags = renderHook(() => hooks.useTags(), { wrapper });
    await waitFor(() => expect(tags.result.current.data).toHaveLength(1));
    expect(api.get).toHaveBeenCalledWith("/api/clientes/tags");

    renderHook(() => hooks.useTiposDocumento(), { wrapper });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/clientes/documentos/tipos"));
  });
});

describe("createCardHubHooks — optimistic writes roll back", () => {
  it("🔴 the tag PUT flips the card at once and restores the snapshot on failure", async () => {
    const hooks = makeHooks();
    const a: Tag = { id: "a", nome: "A", cor: "#111" };
    const b: Tag = { id: "b", nome: "B", cor: "#222" };
    queryClient.setQueryData(hooks.keys.card("c1"), resumo([a]));
    queryClient.setQueryData(hooks.keys.tags, [a, b]);
    let reject!: (e: Error) => void;
    api.put.mockReturnValue(new Promise((_, r) => (reject = r)));
    api.get.mockResolvedValue(resumo([a]));

    const { result } = renderHook(() => hooks.useSetTagsMutation("c1"), { wrapper });
    act(() => {
      result.current.mutate(["a", "b"]);
    });
    await waitFor(() =>
      expect(
        queryClient.getQueryData<CardResumoBase>(hooks.keys.card("c1"))?.tags.map((t) => t.id),
      ).toEqual(["a", "b"]),
    );
    expect(api.put).toHaveBeenCalledWith("/api/clientes/c1/tags", { tag_ids: ["a", "b"] });

    await act(async () => {
      reject(new Error("boom"));
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(
      queryClient.getQueryData<CardResumoBase>(hooks.keys.card("c1"))?.tags.map((t) => t.id),
    ).toEqual(["a"]);
  });

  it("🔴 a checklist tick flips instantly, recounts, and rolls back on failure", async () => {
    const hooks = makeHooks();
    const lista: Checklist[] = [
      {
        id: "cl1",
        titulo: "T",
        posicao: 0,
        origem: "ad_hoc",
        etapa_id: null,
        total_itens: 1,
        concluidos: 0,
        itens: [{ id: "i1", texto: "x", concluido: false, concluido_em: null, concluido_por: null, posicao: 0 }],
      },
    ];
    queryClient.setQueryData(hooks.keys.checklists("c1"), lista);
    let reject!: (e: Error) => void;
    api.patch.mockReturnValue(new Promise((_, r) => (reject = r)));
    api.get.mockResolvedValue({ items: lista, total: 1 });

    const { result } = renderHook(() => hooks.useChecklistMutations("c1"), { wrapper });
    act(() => {
      result.current.toggleItem.mutate({ checklistId: "cl1", itemId: "i1", concluido: true });
    });
    await waitFor(() =>
      expect(queryClient.getQueryData<Checklist[]>(hooks.keys.checklists("c1"))?.[0].concluidos).toBe(1),
    );
    expect(api.patch).toHaveBeenCalledWith("/api/clientes/c1/checklists/cl1/itens/i1", {
      concluido: true,
    });

    await act(async () => {
      reject(new Error("boom"));
    });
    await waitFor(() => expect(result.current.toggleItem.isError).toBe(true));
    expect(queryClient.getQueryData<Checklist[]>(hooks.keys.checklists("c1"))?.[0].itens[0].concluido).toBe(
      false,
    );
  });
});

describe("createCardHubHooks — narrow invalidation", () => {
  it("🔴 a checklist edit invalidates checklists + card + timeline, never documentos", async () => {
    const hooks = makeHooks();
    api.post.mockResolvedValue({ id: "cl9" });
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => hooks.useChecklistMutations("c1"), { wrapper });
    await act(() => result.current.createChecklist.mutateAsync("Nova"));
    const keys = spy.mock.calls.map(([f]) => JSON.stringify((f as { queryKey: unknown }).queryKey));
    expect(keys).toEqual(
      expect.arrayContaining([
        JSON.stringify(["sw", "cardHub", "c1", "checklists"]),
        JSON.stringify(["sw", "cardHub", "c1", "card"]),
        JSON.stringify(["sw", "cardHub", "c1", "timeline"]),
      ]),
    );
    expect(keys).not.toContain(JSON.stringify(["sw", "cardHub", "c1", "documentos"]));
  });

  it("🔴 an upload goes through `api.upload` (multipart) and invalidates the product's extra sub-keys", async () => {
    const hooks = makeHooks();
    api.upload.mockResolvedValue({ id: "d1" });
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => hooks.useDocumentoMutations("c1"), { wrapper });
    const file = new File(["%PDF"], "rg.pdf", { type: "application/pdf" });
    await act(() => result.current.upload.mutateAsync({ file, tipoDocumento: "rg" }));

    expect(api.post).not.toHaveBeenCalled();
    const [path, form] = api.upload.mock.calls[0] as [string, FormData];
    expect(path).toBe("/api/clientes/c1/documentos");
    expect(form.get("tipo_documento")).toBe("rg");
    expect((form.get("file") as File).name).toBe("rg.pdf");

    const keys = spy.mock.calls.map(([f]) => JSON.stringify((f as { queryKey: unknown }).queryKey));
    expect(keys).toEqual(
      expect.arrayContaining([
        JSON.stringify(["sw", "cardHub", "c1", "documentos"]),
        JSON.stringify(["sw", "cardHub", "c1", "card"]),
        JSON.stringify(["sw", "cardHub", "c1", "documento-checklist"]),
        JSON.stringify(["sw", "cardHub", "c1", "timeline"]),
      ]),
    );
  });

  it("a document delete carries `motivo` as a query param (LGPD access log)", async () => {
    const hooks = makeHooks();
    api.delete.mockResolvedValue(undefined);
    const { result } = renderHook(() => hooks.useDocumentoMutations("c1"), { wrapper });
    await act(() => result.current.remove.mutateAsync({ documentoId: "d1", motivo: "Removido pelo usuário" }));
    expect(api.delete).toHaveBeenCalledWith(
      "/api/clientes/c1/documentos/d1?motivo=Removido%20pelo%20usu%C3%A1rio",
    );
  });

  it("the membros PUT names the member source's FK field", async () => {
    const hooks = makeHooks();
    api.put.mockResolvedValue({ items: [], total: 0 });
    const { result } = renderHook(() => hooks.useSetMembrosMutation("c1", "lead_corretor_ids"), {
      wrapper,
    });
    await act(() => result.current.mutateAsync(["m1"]));
    expect(api.put).toHaveBeenCalledWith("/api/clientes/c1/membros", { lead_corretor_ids: ["m1"] });
  });

  it("a descrição nota is created with its tipo", async () => {
    const hooks = makeHooks();
    api.post.mockResolvedValue({ id: "n1" });
    const { result } = renderHook(() => hooks.useNotaMutations("c1"), { wrapper });
    await act(() => result.current.create.mutateAsync({ corpo: "oi", tipo: "descricao" }));
    expect(api.post).toHaveBeenCalledWith("/api/clientes/c1/notas", { corpo: "oi", tipo: "descricao" });
  });
});

describe("cardHubLoadingState — two signals, never isLoading", () => {
  it("skeleton only with no data; refresh indicator only over data", () => {
    expect(cardHubLoadingState({ isPending: true, isFetching: true, data: undefined })).toEqual({
      showSkeleton: true,
      isRefreshing: false,
    });
    expect(cardHubLoadingState({ isPending: false, isFetching: true, data: [] })).toEqual({
      showSkeleton: false,
      isRefreshing: true,
    });
    expect(cardHubLoadingState({ isPending: false, isFetching: false, data: [] })).toEqual({
      showSkeleton: false,
      isRefreshing: false,
    });
  });
});
