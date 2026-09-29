/**
 * Tests for useClientesRevisao hooks — PROJECT.md §5 (the FE↔BE contract),
 * the review-queue slice's primary deliverable.
 *
 * `normalizeRevisaoPage` gets the most attention: §5 doesn't pin whether
 * `GET /api/clientes/revisao` returns a paginated envelope or a bare array
 * (see the file's header comment) — both shapes must work.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, invalidateQueriesMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn }: { queryFn: () => unknown }) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    _queryFn: queryFn,
  }));
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown, v: unknown) => void;
    }) => ({
      mutateAsync: async (vars: unknown) => {
        const result = await mutationFn(vars);
        onSuccess?.(result, vars);
        return result;
      },
      mutate: (
        vars: unknown,
        opts?: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void },
      ) => {
        Promise.resolve(mutationFn(vars))
          .then((result) => {
            onSuccess?.(result, vars);
            opts?.onSuccess?.(result);
          })
          .catch((err) => opts?.onError?.(err));
      },
      isPending: false,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  normalizeRevisaoPage,
  useRevisaoFila,
  useRevisaoMutations,
  useRevisaoCpfFila,
  useRevisaoCpfMutations,
  type RevisaoGrupo,
  type RevisaoCpfGrupo,
} from "./useClientesRevisao";

beforeEach(() => {
  vi.clearAllMocks();
});

function grupo(overrides: Partial<RevisaoGrupo> = {}): RevisaoGrupo {
  return {
    motivo: "C5",
    chave_canonica: "+5511974781330",
    candidatos: [
      { id: "cand1", nome: "Maria Silva", chave_canonica: "+5511974781330", touch_count: 4 },
      { id: "cand2", nome: "João Souza", chave_canonica: "+5511974781330", touch_count: 2 },
    ],
    ...overrides,
  };
}

describe("normalizeRevisaoPage", () => {
  it("passes through a paginated envelope unchanged", () => {
    const envelope = { items: [grupo()], total: 311, page: 1, pages: 26 };
    expect(normalizeRevisaoPage(envelope, { page: 1 })).toEqual(envelope);
  });

  it("paginates a bare array client-side when the backend has no server-side pagination", () => {
    const groups = Array.from({ length: 5 }, (_, i) => grupo({ chave_canonica: `+551190000000${i}` }));
    const result = normalizeRevisaoPage(groups, { page: 2, page_size: 2 });
    expect(result.total).toBe(5);
    expect(result.pages).toBe(3);
    expect(result.page).toBe(2);
    expect(result.items.map((g) => g.chave_canonica)).toEqual(["+5511900000002", "+5511900000003"]);
  });

  it("returns an empty page for a bare-null response, never throws", () => {
    expect(normalizeRevisaoPage(null, { page: 1 })).toEqual({
      items: [],
      total: 0,
      page: 1,
      pages: 1,
    });
  });
});

describe("useRevisaoFila", () => {
  it("GETs /api/clientes/revisao with page/page_size", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useRevisaoFila({ page: 1, page_size: 12 }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/revisao?page=1&page_size=12");
  });
});

describe("useRevisaoMutations", () => {
  it("POSTs .../merge with no body when no survivor is chosen", async () => {
    mockPost.mockResolvedValue({ merge_id: "m1" });
    const { merge } = useRevisaoMutations();
    const result = await (merge as any).mutateAsync({ grupoId: "g1" });
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/revisao/g1/merge", undefined);
    expect(result).toEqual({ merge_id: "m1" });
    // Merging must invalidate BOTH the queue and the board — a merged
    // group must disappear from the queue AND collapse to one card there.
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["sw", "clientes", "revisao"],
    });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["sw", "clientes", "board"],
    });
  });

  it("POSTs .../manter-separados and invalidates only the queue", async () => {
    mockPost.mockResolvedValue({});
    const { manterSeparados } = useRevisaoMutations();
    await (manterSeparados as any).mutateAsync("g1");
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/revisao/g1/manter-separados");
  });

  it("POSTs /api/clientes/merges/{id}/desfazer to undo (D3)", async () => {
    mockPost.mockResolvedValue({});
    const { desfazer } = useRevisaoMutations();
    await (desfazer as any).mutateAsync("m1");
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/merges/m1/desfazer");
  });
});

// ─── CPF axis (2026-09-28) ───────────────────────────────────────────────────

function cpfGrupo(overrides: Partial<RevisaoCpfGrupo> = {}): RevisaoCpfGrupo {
  return {
    motivo: "CPF",
    chave_canonica: "12345678901",
    candidatos: [
      { id: "cli1", nome: "Maria Silva", cpf: "12345678901" } as any,
      { id: "cli2", nome: "Maria S. Silva", cpf: "12345678901" } as any,
    ],
    ...overrides,
  };
}

describe("useRevisaoCpfFila", () => {
  it("GETs /api/clientes/revisao-cpf with page/page_size", async () => {
    mockGet.mockResolvedValue({ items: [cpfGrupo()], total: 1, page: 1, pages: 1 });
    const hook = useRevisaoCpfFila({ page: 1, page_size: 12 }) as any;
    const result = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/revisao-cpf?page=1&page_size=12");
    expect(result.items[0].chave_canonica).toBe("12345678901");
  });

  it("GETs with no query string when no filters are given", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useRevisaoCpfFila() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/revisao-cpf");
  });
});

describe("useRevisaoCpfMutations", () => {
  it("POSTs .../revisao-cpf/{grupo}/merge with the EXPLICIT survivor (unlike the identity axis)", async () => {
    mockPost.mockResolvedValue({ cliente_id: "cli2", merged_ids: ["cli1"], merge_ids: ["m1"] });
    const { merge } = useRevisaoCpfMutations();
    const result = await (merge as any).mutateAsync({
      grupoId: "12345678901",
      clienteIdSobrevivente: "cli2",
    });
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/revisao-cpf/12345678901/merge", {
      cliente_id_sobrevivente: "cli2",
    });
    expect(result).toEqual({ cliente_id: "cli2", merged_ids: ["cli1"], merge_ids: ["m1"] });
    // Same double-invalidation as the identity axis: a merged group must
    // disappear from the queue AND collapse to one card on the board.
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["sw", "clientes", "revisao-cpf"],
    });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["sw", "clientes", "board"],
    });
  });

  it("POSTs .../revisao-cpf/{grupo}/manter-separados with no body", async () => {
    mockPost.mockResolvedValue({ cpf_normalizado: "12345678901", rejeitado: true });
    const { manterSeparados } = useRevisaoCpfMutations();
    await (manterSeparados as any).mutateAsync("12345678901");
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/revisao-cpf/12345678901/manter-separados");
  });
});
