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
  useCompradorMutations,
  useDadosPessoaisMutation,
  useDecidirConflitoMutation,
  useDocumentoMutations,
  useResolverConflitosAutomaticamente,
  contagemResolverConflitos,
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

  it("reextrair() POSTs to .../extrair via the normal api.post() — no body, the document id travels in the path", async () => {
    mockPost.mockResolvedValue({ id: "doc1", extracao_status: "pendente" });
    const { reextrair } = useDocumentoMutations("cl1");
    await (reextrair as any).mutateAsync("doc1");

    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cl1/documentos/doc1/extrair");
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

describe("useCompradorMutations.atualizarPapel — o papel da parte", () => {
  it("PATCHes the parte and sends ONLY the papel", async () => {
    mockPatch.mockResolvedValue({ id: "p1", papel: "conjuge", conjuge_cliente_id: "cl1" });
    const { atualizarPapel } = useCompradorMutations("cl1");
    await (atualizarPapel as any).mutateAsync({ parteId: "p1", papel: "conjuge" });

    // 🔴 No `lado` in the body. `lado` decides which vocabulary validates
    // `papel` (`PAPEIS_POR_LADO`), so a client able to name it could call a
    // vendedor a `fiador`; the server reads the side off the stored row.
    expect(mockPatch).toHaveBeenCalledWith("/api/clientes/cl1/compradores/p1", {
      papel: "conjuge",
    });
  });

  it("invalidates BOTH sides, not just the one written", async () => {
    mockPatch.mockResolvedValue({ id: "p1", papel: "conjuge" });
    const { atualizarPapel } = useCompradorMutations("cl1");
    await (atualizarPapel as any).mutateAsync({ parteId: "p1", papel: "conjuge" });

    // The key stops at "compradores" — no `lado` segment — because setting
    // `conjuge` can also write `clientes.conjuge_cliente_id` on two people,
    // so the card is no longer only about this one list.
    const keys = invalidateQueriesMock.mock.calls.map(([arg]: any[]) =>
      JSON.stringify(arg.queryKey),
    );
    expect(keys).toContain(JSON.stringify(["sw", "cardHub", "cl1", "compradores"]));
    expect(keys).toContain(JSON.stringify(["sw", "cardHub", "cl1", "card"]));
  });

  it("propagates the 409 the spouse guard raises, message intact", async () => {
    mockPatch.mockRejectedValue(
      new Error("[409] Esta pessoa já tem outro cônjuge vinculado — corrija o cadastro dela antes de marcar este vínculo."),
    );
    const { atualizarPapel } = useCompradorMutations("cl1");
    // Swallowing it would drop the ONE instruction the refusal carries.
    await expect(
      (atualizarPapel as any).mutateAsync({ parteId: "p1", papel: "conjuge" }),
    ).rejects.toThrow("outro cônjuge vinculado");
  });
});

describe("useDadosPessoaisMutation — Bug F: a save must not leave Qualificação stale", () => {
  it("🔴 invalidates the qualificação-completude key on save success", async () => {
    mockPatch.mockResolvedValue({ nome_completo: "Ana" });
    const mutation = useDadosPessoaisMutation("cl1") as any;
    await mutation.mutateAsync({ nome_completo: "Ana" });

    // Rooted, not per-cliente-exact — invalidating the ROOT key is what
    // reaches every party's cached `QualificacaoCompletudePanel` entry, not
    // only the titular's.
    const keys = invalidateQueriesMock.mock.calls.map(([arg]: any[]) =>
      JSON.stringify(arg.queryKey),
    );
    expect(keys).toContain(JSON.stringify(["sw", "cardHub", "qualificacao"]));
    expect(keys).toContain(JSON.stringify(["sw", "cardHub", "cl1", "card"]));
  });
});

describe("useDadosPessoaisMutation — a PARTY's save reaches the titular's card", () => {
  it("🔴 invalidates every card's compradores list, not only the saved person's", async () => {
    mockPatch.mockResolvedValue({ cpf: "52998224725" });
    // Instantiated with the PARTY's id — the titular's card that lists this
    // party is keyed under a different id the mutation never learns.
    const mutation = useDadosPessoaisMutation("parte-cliente") as any;
    await mutation.mutateAsync({ cpf: "52998224725" });

    const predicados = invalidateQueriesMock.mock.calls
      .map(([arg]: any[]) => arg?.predicate)
      .filter(Boolean);
    const alcanca = (queryKey: unknown[]) => predicados.some((p: any) => p({ queryKey }));
    expect(alcanca(["sw", "cardHub", "titular-1", "compradores", "comprador"])).toBe(true);
    expect(alcanca(["sw", "cardHub", "titular-1", "compradores", "vendedor"])).toBe(true);
    expect(alcanca(["sw", "cardHub", "titular-1", "card"])).toBe(false);
    expect(alcanca(["sw", "clientes", "titular-1", "compradores"])).toBe(false);
  });
});

describe("useDadosPessoaisMutation — body carries ONLY ClientePatchBody's columns", () => {
  it("🔴 strips non-editable cliente columns a wider seed object carries (the prod 422)", async () => {
    mockPatch.mockResolvedValue({ celular: "11999999999" });
    const mutation = useDadosPessoaisMutation("cl1") as any;
    // What `ClienteDetailModal` actually hands the form: the full `clientes`
    // row merged under the checklist `valores`. Every one of these extra keys
    // made `StrictHttpModel` answer "Extra inputs are not permitted".
    await mutation.mutateAsync({
      id: "cl1",
      org_id: "org1",
      ativo: true,
      created_at: "2026-09-24T17:47:06Z",
      chave_canonica: null,
      cpf_origem: null,
      identidade_incerta: true,
      nome: "KLEBER",
      celular: "11999999999",
      estado_civil: null,
    });

    expect(mockPatch).toHaveBeenCalledWith("/api/clientes/cl1", {
      celular: "11999999999",
      estado_civil: null,
    });
  });
});

describe("useDecidirConflitoMutation — Bug F, reverse direction (admin decision)", () => {
  it("🔴 invalidates the qualificação-completude key when a conflict is decided", async () => {
    mockPut.mockResolvedValue({ id: "cf1", cliente_id: "cl1" });
    const mutation = useDecidirConflitoMutation() as any;
    await mutation.mutateAsync({ conflitoId: "cf1", aceitar: true });

    const keys = invalidateQueriesMock.mock.calls.map(([arg]: any[]) =>
      JSON.stringify(arg.queryKey),
    );
    expect(keys).toContain(JSON.stringify(["sw", "cardHub", "qualificacao"]));
  });
});

// ─── Roteiro PDF download — the server names the file ─────────────────────
describe("nomeDoArquivo / baixarRoteiroPdf", () => {
  it("reads the plain and the RFC 5987 forms, else null", async () => {
    const { nomeDoArquivo } = await import("./useCardHub");
    expect(nomeDoArquivo('attachment; filename="roteiro-ab12cd34-2026-10-10.pdf"')).toBe(
      "roteiro-ab12cd34-2026-10-10.pdf",
    );
    expect(nomeDoArquivo("attachment; filename*=UTF-8''roteiro%20x.pdf")).toBe("roteiro x.pdf");
    expect(nomeDoArquivo("attachment")).toBeNull();
    expect(nomeDoArquivo(null)).toBeNull();
  });

  it("downloads under the Content-Disposition name, falling back to the id-only name", async () => {
    const { baixarRoteiroPdf } = await import("./useCardHub");
    const nomes: string[] = [];
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        nomes.push(this.download);
      });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const resposta = (disposition: string | null) => ({
      ok: true,
      status: 200,
      blob: async () => new Blob(["%PDF-"]),
      headers: new Headers(disposition ? { "Content-Disposition": disposition } : {}),
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(resposta('attachment; filename="roteiro-ab12cd34-2026-10-10.pdf"'))
      .mockResolvedValueOnce(resposta(null));
    vi.stubGlobal("fetch", fetchMock);

    await baixarRoteiroPdf("cli-1", "ab12cd34-0000");
    await baixarRoteiroPdf("cli-1", "ab12cd34-0000");

    expect(nomes).toEqual(["roteiro-ab12cd34-2026-10-10.pdf", "roteiro-ab12cd34.pdf"]);
    click.mockRestore();
    vi.unstubAllGlobals();
  });
});

describe("useResolverConflitosAutomaticamente", () => {
  it("🔴 POSTs the org-wide sweep and invalidates every surface it can move", async () => {
    mockPost.mockResolvedValue({ resolvidos: [], ainda_pendentes: [], ignorado_composto: [], imoveis: {} });
    const mutation = useResolverConflitosAutomaticamente() as any;
    await mutation.mutateAsync(undefined);
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/conflitos/resolver-automaticamente", {});
    const keys = invalidateQueriesMock.mock.calls.map(([arg]: any[]) => JSON.stringify(arg.queryKey));
    expect(keys).toContain(JSON.stringify(["sw", "cardHub", "conflitos"]));
    expect(keys).toContain(JSON.stringify(["sw", "cardHub"]));
    expect(keys).toContain(JSON.stringify(["sw", "clientes"]));
    expect(keys).toContain(JSON.stringify(["sw", "imovel-dados"]));
  });

  it("counts lists for the cliente queue and numbers for the imóvel queue", () => {
    expect(
      contagemResolverConflitos({
        resolvidos: [1, 2],
        ainda_pendentes: [3],
        ignorado_composto: [4],
        imoveis: { resolvidos: 5, ainda_pendentes: 6, ignorados: 7 },
      }),
    ).toEqual({
      clientes: { resolvidos: 2, aindaPendentes: 1, ignorados: 1 },
      imoveis: { resolvidos: 5, aindaPendentes: 6, ignorados: 7 },
    });
    expect(contagemResolverConflitos(null).imoveis.resolvidos).toBe(0);
  });
});
