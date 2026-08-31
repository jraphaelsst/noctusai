/**
 * Tests for `useEsteira` — the refetch-unmount regression (fleet audit,
 * 2026-08-31) plus the `moverTarefa` optimistic-update follow-up.
 *
 * Mocks `@tanstack/react-query` itself (mirrors
 * `products/social-wiring/frontend/src/hooks/useClientes.test.ts`), so
 * `useQuery`/`useMutation` return a controllable stand-in and the hook's
 * OWN `loading`/`onMutate`/`onError` logic runs for real — this is not a
 * page-level stub of the hook, it exercises the actual formula that broke.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockCancelQueries, mockGetQueryData, mockSetQueryData, mockInvalidateQueries } =
  vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockPost: vi.fn(),
    mockCancelQueries: vi.fn(),
    mockGetQueryData: vi.fn(),
    mockSetQueryData: vi.fn(),
    mockInvalidateQueries: vi.fn(),
  }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(
    (opts: { queryKey: unknown }) =>
      ({
        data: undefined,
        isPending: true,
        isFetching: true,
        isError: false,
        error: null,
        _queryKey: opts.queryKey,
      }) as unknown,
  );
  // Captures the FULL options object (not just mutationFn) so a test can
  // invoke onMutate/onError directly — that is where the optimistic-update
  // logic under test actually lives.
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, isPending: false }));
  const useQueryClient = vi.fn(() => ({
    cancelQueries: mockCancelQueries,
    getQueryData: mockGetQueryData,
    setQueryData: mockSetQueryData,
    invalidateQueries: mockInvalidateQueries,
  }));
  return { useQuery, useMutation, useQueryClient };
});

import { useQuery } from "@tanstack/react-query";
import {
  useApontamentos,
  useAprovacaoPublica,
  useMoverTarefa,
  useQuadro,
  type Quadro,
} from "./useEsteira";

const mockUseQuery = vi.mocked(useQuery);

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── loading formula: isPending && !data, never || isFetching ─────────────

describe("useQuadro — loading formula", () => {
  it("is true on first load: isPending true, no data yet", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    const { loading, quadro } = useQuadro();

    expect(loading).toBe(true);
    expect(quadro).toBeNull();
  });

  it("REGRESSION: is false mid-background-refetch once data exists — the bug", () => {
    // isPending false + isFetching true is exactly what TanStack v5 reports
    // right after a mutation invalidates the quadro. The old
    // `isPending || isFetching` gate was still `true` here, which unmounted
    // the whole kanban board on every card move / timer toggle.
    const data: Quadro = { etapas: ["aguardando_roteiro"], colunas: { aguardando_roteiro: [] } as never };
    mockUseQuery.mockReturnValue({
      data,
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    const { loading, quadro } = useQuadro();

    expect(loading).toBe(false);
    expect(quadro).toBe(data);
  });

  it("is false once settled with no background fetch in flight", () => {
    const data: Quadro = { etapas: [], colunas: {} as never };
    mockUseQuery.mockReturnValue({
      data,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    } as never);

    expect(useQuadro().loading).toBe(false);
  });
});

describe("useApontamentos — loading formula (same shape as useQuadro)", () => {
  it("does not report loading while data exists and a refetch is in flight", () => {
    mockUseQuery.mockReturnValue({
      data: [],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    expect(useApontamentos("tarefa-1").loading).toBe(false);
  });
});

describe("useAprovacaoPublica — loading formula", () => {
  it("does not report loading while the client's aprovação is on screen mid-refetch", () => {
    mockUseQuery.mockReturnValue({
      data: { titulo: "x", pecas: [], copy_texto: null, direcao_video: null, formato: null, cliente_nome: null, ja_decidida: false },
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    expect(useAprovacaoPublica("token-1").loading).toBe(false);
  });

  it("REGRESSION: never reports non-loading empty state before the FIRST fetch settles", () => {
    // `aprovacao` must stay null (never a synthesized empty object) while
    // pending — the caller's `error || !aprovacao` branch is what renders
    // "link inválido"; if this flipped to non-null before data ever arrived
    // a real, still-loading approval token would flash as invalid.
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    const { loading, aprovacao } = useAprovacaoPublica("token-1");
    expect(loading).toBe(true);
    expect(aprovacao).toBeNull();
  });
});

// ─── moverTarefa — optimistic update (Category D) ──────────────────────────

const QUADRO: Quadro = {
  etapas: ["aguardando_roteiro", "roteiro_em_producao"],
  colunas: {
    aguardando_roteiro: [
      {
        id: "tarefa-1",
        org_id: "org-1",
        pauta_id: "pauta-1",
        titulo: "Reels de lançamento",
        etapa: "aguardando_roteiro",
        responsavel_id: null,
        prazo: null,
        refacoes: 0,
        observacao_cliente: null,
        created_at: null,
        updated_at: null,
      },
    ],
    roteiro_em_producao: [],
  } as never,
};

describe("useMoverTarefa — optimistic move", () => {
  it("onMutate moves the tarefa into the target column BEFORE the request settles", async () => {
    mockGetQueryData.mockReturnValue(QUADRO);
    const mover = useMoverTarefa() as unknown as {
      onMutate: (vars: { id: string; etapa: string }) => Promise<{ previous: Quadro | undefined }>;
    };

    const context = await mover.onMutate({ id: "tarefa-1", etapa: "roteiro_em_producao" });

    expect(mockCancelQueries).toHaveBeenCalled();
    // Snapshot returned for rollback.
    expect(context.previous).toBe(QUADRO);
    // The board was optimistically rewritten: gone from the source column,
    // present in the target column, with its `etapa` field updated too.
    expect(mockSetQueryData).toHaveBeenCalledTimes(1);
    const [, updater] = mockSetQueryData.mock.calls[0] as [unknown, Quadro];
    expect(updater.colunas.aguardando_roteiro).toHaveLength(0);
    expect(updater.colunas.roteiro_em_producao).toHaveLength(1);
    expect(updater.colunas.roteiro_em_producao[0]).toMatchObject({
      id: "tarefa-1",
      etapa: "roteiro_em_producao",
    });
  });

  it("onError restores the pre-move board from the snapshot", () => {
    const mover = useMoverTarefa() as unknown as {
      onError: (err: unknown, vars: unknown, context: { previous: Quadro }) => void;
    };

    mover.onError(new Error("network"), { id: "tarefa-1", etapa: "roteiro_em_producao" }, {
      previous: QUADRO,
    });

    expect(mockSetQueryData).toHaveBeenCalledWith(expect.anything(), QUADRO);
  });

  it("does nothing destructive when there is no cached quadro to snapshot", async () => {
    mockGetQueryData.mockReturnValue(undefined);
    const mover = useMoverTarefa() as unknown as {
      onMutate: (vars: { id: string; etapa: string }) => Promise<{ previous: Quadro | undefined }>;
    };

    const context = await mover.onMutate({ id: "tarefa-1", etapa: "roteiro_em_producao" });

    expect(context.previous).toBeUndefined();
    expect(mockSetQueryData).not.toHaveBeenCalled();
  });
});
