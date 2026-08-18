/**
 * useCardHub.test.ts — lead-card-hub-p2-PROJECT.md §3. Mirrors
 * `useClientes.test.ts`'s mocking pattern exactly (mock `@tanstack/react-query`
 * itself so `_queryFn`/`_mutationFn` are invokable directly, mock
 * `@noctusai/seed/infra`'s `api`/`supabase`), extended with a stub
 * `useInfiniteQuery` for the timeline.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockPatch, mockPut, mockDelete, invalidateQueriesMock, cancelQueriesMock, setQueryDataMock, getQueryDataMock } =
  vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockPost: vi.fn(),
    mockPatch: vi.fn(),
    mockPut: vi.fn(),
    mockDelete: vi.fn(),
    invalidateQueriesMock: vi.fn(),
    cancelQueriesMock: vi.fn(),
    setQueryDataMock: vi.fn(),
    getQueryDataMock: vi.fn(),
  }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete },
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "tok123" } } }),
    },
  },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn, enabled }: any) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    _queryFn: queryFn,
    _enabled: enabled,
  }));
  const useInfiniteQuery = vi.fn(({ queryFn, enabled, getNextPageParam, initialPageParam }: any) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    _queryFn: queryFn,
    _enabled: enabled,
    _getNextPageParam: getNextPageParam,
    _initialPageParam: initialPageParam,
  }));
  const useMutation = vi.fn(({ mutationFn, onMutate, onError, onSuccess, onSettled }: any) => ({
    mutateAsync: async (vars: unknown) => {
      const context = await onMutate?.(vars);
      try {
        const result = await mutationFn(vars);
        await onSuccess?.(result, vars);
        return result;
      } catch (err) {
        await onError?.(err, vars, context);
        throw err;
      } finally {
        await onSettled?.(undefined, null, vars);
      }
    },
    mutate: (vars: unknown, opts?: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }) => {
      Promise.resolve()
        .then(async () => {
          const context = await onMutate?.(vars);
          try {
            const result = await mutationFn(vars);
            await onSuccess?.(result, vars);
            opts?.onSuccess?.(result);
            return result;
          } catch (err) {
            onError?.(err, vars, context);
            opts?.onError?.(err);
            throw err;
          } finally {
            await onSettled?.(undefined, null, vars);
          }
        })
        .catch(() => {});
    },
    isPending: false,
    _mutationFn: mutationFn,
  }));
  const useQueryClient = vi.fn(() => ({
    invalidateQueries: invalidateQueriesMock,
    cancelQueries: cancelQueriesMock,
    setQueryData: setQueryDataMock,
    getQueryData: getQueryDataMock,
  }));
  return { useQuery, useInfiniteQuery, useMutation, useQueryClient };
});

import {
  flattenTimeline,
  useCardResumo,
  useChecklistMutations,
  useDatasMutation,
  useDocumentoMutations,
  useNotaMutations,
  useSetClienteTagsMutation,
  useTags,
  useTimeline,
} from "./useCardHub";

beforeEach(() => {
  vi.clearAllMocks();
  (globalThis as any).fetch = vi.fn();
});

describe("useCardResumo", () => {
  it("GETs /api/clientes/{id}/card", async () => {
    mockGet.mockResolvedValue({ cliente: {}, tags: [], membros: [], datas: {}, badges: {}, atendimentos: [] });
    const hook = useCardResumo("cl1") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cl1/card");
  });

  it("is disabled when clienteId is null", () => {
    const hook = useCardResumo(null) as any;
    expect(hook._enabled).toBe(false);
  });
});

describe("useTimeline", () => {
  it("GETs the timeline with limit=50 and no cursor on the first page", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, next_cursor: null });
    const hook = useTimeline("cl1") as any;
    await hook._queryFn({ pageParam: null });
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cl1/timeline?limit=50");
  });

  it("appends cursor and kinds when given", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, next_cursor: null });
    const hook = useTimeline("cl1", ["nota", "touch"]) as any;
    await hook._queryFn({ pageParam: "abc" });
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cl1/timeline?limit=50&cursor=abc&kinds=nota%2Ctouch");
  });

  it("flattenTimeline flattens pages into one array", () => {
    const flat = flattenTimeline([
      { items: [{ id: "1" }] as any, total: 2, next_cursor: "x" },
      { items: [{ id: "2" }] as any, total: 2, next_cursor: null },
    ]);
    expect(flat.map((e) => e.id)).toEqual(["1", "2"]);
  });

  it("flattenTimeline returns [] for undefined pages", () => {
    expect(flattenTimeline(undefined)).toEqual([]);
  });
});

describe("useTags", () => {
  it("GETs the org tag catalogue and unwraps items", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "t1", nome: "Urgente", cor: "#eb5a46" }], total: 1 });
    const hook = useTags() as any;
    const result = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/tags");
    expect(result).toEqual([{ id: "t1", nome: "Urgente", cor: "#eb5a46" }]);
  });
});

describe("useSetClienteTagsMutation — optimistic with rollback", () => {
  it("PUTs the full tag id set", async () => {
    mockPut.mockResolvedValue({ items: [], total: 0 });
    const mutation = useSetClienteTagsMutation("cl1") as any;
    await mutation.mutateAsync(["t1", "t2"]);
    expect(mockPut).toHaveBeenCalledWith("/api/clientes/cl1/tags", { tag_ids: ["t1", "t2"] });
  });

  it("rolls back the cache to the pre-toggle snapshot on failure", async () => {
    const previousCard = { tags: [{ id: "t1", nome: "A", cor: "#000" }] };
    getQueryDataMock.mockImplementation((key: any) =>
      key[key.length - 1] === "card" ? previousCard : undefined,
    );
    mockPut.mockRejectedValue(new Error("boom"));

    const mutation = useSetClienteTagsMutation("cl1") as any;
    await expect(mutation.mutateAsync(["t2"])).rejects.toThrow("boom");

    // onError restores the snapshot captured in onMutate's context.
    expect(setQueryDataMock).toHaveBeenCalledWith(expect.anything(), previousCard);
  });
});

describe("useChecklistMutations.toggleItem — optimistic checkbox", () => {
  it("PATCHes concluido and rolls back the checklist list on failure", async () => {
    const previous = [
      {
        id: "cl1",
        titulo: "Checklist",
        itens: [{ id: "i1", concluido: false }],
        concluidos: 0,
        total_itens: 1,
      },
    ];
    getQueryDataMock.mockReturnValue(previous);
    mockPatch.mockRejectedValue(new Error("network down"));

    const { toggleItem } = useChecklistMutations("cl1");
    await expect(
      (toggleItem as any).mutateAsync({ checklistId: "cl1", itemId: "i1", concluido: true }),
    ).rejects.toThrow("network down");

    expect(setQueryDataMock).toHaveBeenCalledWith(expect.anything(), previous);
  });

  it("flips concluido optimistically before the server responds", async () => {
    const previous = [
      { id: "cl1", titulo: "Checklist", itens: [{ id: "i1", concluido: false }], concluidos: 0, total_itens: 1 },
    ];
    getQueryDataMock.mockReturnValue(previous);
    mockPatch.mockResolvedValue({});

    const { toggleItem } = useChecklistMutations("cl1");
    await (toggleItem as any).mutateAsync({ checklistId: "cl1", itemId: "i1", concluido: true });

    const optimisticCall = setQueryDataMock.mock.calls.find(
      (call) => Array.isArray(call[1]) && call[1][0]?.itens?.[0]?.concluido === true,
    );
    expect(optimisticCall).toBeTruthy();
  });
});

describe("useDatasMutation", () => {
  it("PATCHes /api/clientes/{id}/datas with the given body", async () => {
    mockPatch.mockResolvedValue({
      data_inicio: null,
      data_entrega: "2026-08-20T00:00:00Z",
      entrega_concluida: false,
      lembrete_minutos_antes: 1440,
      recorrencia: null,
      proximo_lembrete: { id: "r1", dispara_em: "2026-08-19T00:00:00Z" },
    });
    const mutation = useDatasMutation("cl1") as any;
    await mutation.mutateAsync({ data_entrega: "2026-08-20T00:00:00Z", lembrete_minutos_antes: 1440 });
    expect(mockPatch).toHaveBeenCalledWith("/api/clientes/cl1/datas", {
      data_entrega: "2026-08-20T00:00:00Z",
      lembrete_minutos_antes: 1440,
    });
  });
});

describe("useDocumentoMutations", () => {
  it("upload() POSTs multipart via raw fetch with the auth header, never the JSON api client", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ id: "doc1", nome_original: "a.pdf" }),
    });
    const { upload } = useDocumentoMutations("cl1");
    const file = new File(["x"], "a.pdf", { type: "application/pdf" });
    await (upload as any).mutateAsync({ file, tipoDocumento: "outro" });

    expect(globalThis.fetch).toHaveBeenCalledOnce();
    const [url, init] = (globalThis.fetch as any).mock.calls[0];
    expect(url).toContain("/api/clientes/cl1/documentos");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok123");
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("remove() sends motivo as a REQUIRED query param via the normal api.delete() — the backend route takes it that way, not a body", async () => {
    mockDelete.mockResolvedValue(undefined);
    const { remove } = useDocumentoMutations("cl1");
    await (remove as any).mutateAsync({ documentoId: "doc1", motivo: "Removido pelo usuário" });

    expect(mockDelete).toHaveBeenCalledWith(
      "/api/clientes/cl1/documentos/doc1?motivo=Removido%20pelo%20usu%C3%A1rio",
    );
    // No raw-fetch DELETE for this route anymore — the seed api client's
    // delete() has no body parameter, but this route no longer needs one.
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("useNotaMutations — tipo discriminator (descricao vs. comentario)", () => {
  it("create() defaults tipo to comentario when omitted", async () => {
    mockPost.mockResolvedValue({ id: "n1", tipo: "comentario", corpo: "oi", autor: null, editado_em: null, deleted_at: null });
    const { create } = useNotaMutations("cl1");
    await (create as any).mutateAsync({ corpo: "oi" });
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cl1/notas", { corpo: "oi", tipo: "comentario" });
  });

  it("create() sends tipo: descricao when creating the description", async () => {
    mockPost.mockResolvedValue({ id: "n2", tipo: "descricao", corpo: "desc", autor: null, editado_em: null, deleted_at: null });
    const { create } = useNotaMutations("cl1");
    await (create as any).mutateAsync({ corpo: "desc", tipo: "descricao" });
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cl1/notas", { corpo: "desc", tipo: "descricao" });
  });

  it("create() propagates a 409 (duplicate descricao) as a rejected promise carrying the server message, never swallowed", async () => {
    mockPost.mockRejectedValue(
      new Error("[409] Este cliente já possui uma descrição — edite a existente em vez de criar outra."),
    );
    const { create } = useNotaMutations("cl1");
    await expect((create as any).mutateAsync({ corpo: "desc", tipo: "descricao" })).rejects.toThrow(
      "já possui uma descrição",
    );
  });
});
