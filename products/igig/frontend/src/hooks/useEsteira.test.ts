/**
 * Tests for `useEsteira` — the board descriptor on the seed pipeline, the
 * tarefa writes (create / delete / timer / link) and the loading formulas.
 *
 * Mocks `@tanstack/react-query` itself (mirrors
 * `products/social-wiring/frontend/src/hooks/useClientes.test.ts`), so
 * `useQuery`/`useMutation` return a controllable stand-in and the hook's OWN
 * derivations (`loading`, `emAndamento`, `minutosTotais`) and `mutationFn`s run
 * for real.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPost, mockDelete, mockInvalidateQueries } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
  mockInvalidateQueries: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, delete: mockDelete, patch: vi.fn() },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(
    () =>
      ({
        data: undefined,
        isPending: true,
        isFetching: true,
        isError: false,
        error: null,
      }) as unknown,
  );
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: mockInvalidateQueries }));
  return { useQuery, useMutation, useQueryClient, keepPreviousData: (prev: unknown) => prev };
});

import { useQuery } from "@tanstack/react-query";
import {
  ESTEIRA_BOARD_KEY,
  esteiraPipeline,
  urlAprovacao,
  useApontamentos,
  useAprovacaoPublica,
  useCriarTarefa,
  useEmitirLinkAprovacao,
  useEncerrarTimer,
  useExcluirTarefa,
  useIniciarTimer,
  type Apontamento,
} from "./useEsteira";

const mockUseQuery = vi.mocked(useQuery);

type MutationStub = {
  mutationFn: (vars: unknown) => Promise<unknown>;
  onSuccess: () => void;
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("esteiraPipeline — the board descriptor", () => {
  it("reads the stage-based board, moves through mover-etapa and edits stages", () => {
    const d = esteiraPipeline.descriptor;
    expect(d.boardEndpoint).toBe("/api/esteira/board");
    expect(d.moveEndpoint).toBe("/api/esteira/tarefas");
    expect(d.stagesEndpoint).toBe("/api/esteira/stages");
    expect(d.queryKey).toBe(ESTEIRA_BOARD_KEY);
  });

  it("never points at the removed legacy /quadro endpoint", () => {
    expect(JSON.stringify(esteiraPipeline.descriptor)).not.toContain("quadro");
  });
});

describe("tarefa writes", () => {
  it("creates a tarefa from a pauta and refreshes the board", async () => {
    const m = useCriarTarefa() as unknown as MutationStub;
    await m.mutationFn({ pauta_id: "p1", titulo: "Arte" });
    expect(mockPost).toHaveBeenCalledWith("/api/esteira/tarefas", { pauta_id: "p1", titulo: "Arte" });
    m.onSuccess();
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: [ESTEIRA_BOARD_KEY] });
  });

  it("deletes through DELETE /api/esteira/tarefas/{id} and refreshes the board", async () => {
    const m = useExcluirTarefa() as unknown as MutationStub;
    await m.mutationFn("t1");
    expect(mockDelete).toHaveBeenCalledWith("/api/esteira/tarefas/t1");
    m.onSuccess();
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: [ESTEIRA_BOARD_KEY] });
  });

  it("starts and stops the timer WITHOUT a usuario_id (the server times the caller)", async () => {
    await (useIniciarTimer() as unknown as MutationStub).mutationFn("t1");
    await (useEncerrarTimer() as unknown as MutationStub).mutationFn("t1");
    expect(mockPost).toHaveBeenNthCalledWith(1, "/api/esteira/tarefas/t1/timer/iniciar");
    expect(mockPost).toHaveBeenNthCalledWith(2, "/api/esteira/tarefas/t1/timer/encerrar");
  });

  it("minting the approval link refreshes the board (the card moves into approval)", async () => {
    const m = useEmitirLinkAprovacao() as unknown as MutationStub;
    await m.mutationFn("t1");
    expect(mockPost).toHaveBeenCalledWith("/api/esteira/tarefas/t1/link-aprovacao", {});
    m.onSuccess();
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: [ESTEIRA_BOARD_KEY] });
  });

  it("builds the public approval URL from the token", () => {
    expect(urlAprovacao("abc", "https://igig.noctusai.com")).toBe(
      "https://igig.noctusai.com/aprovar/abc",
    );
  });
});

const seg = (over: Partial<Apontamento>): Apontamento => ({
  id: "a",
  org_id: "o",
  tarefa_id: "t1",
  usuario_id: "eu",
  profissional_id: null,
  iniciado_em: "2026-09-23T10:00:00Z",
  encerrado_em: "2026-09-23T10:30:00Z",
  minutos: 30,
  ...over,
});

describe("useApontamentos", () => {
  it("finds MY open segment — not a colleague's — as the running timer", () => {
    mockUseQuery.mockReturnValue({
      data: [
        seg({ id: "1" }),
        seg({ id: "2", usuario_id: "colega", encerrado_em: null, minutos: 0 }),
        seg({ id: "3", encerrado_em: null, minutos: 0 }),
      ],
      isPending: false,
      isFetching: false,
    } as never);
    const r = useApontamentos("t1", "eu");
    expect(r.emAndamento?.id).toBe("3");
    expect(r.minutosTotais).toBe(30);
  });

  it("reports no running timer when only a colleague's is open", () => {
    mockUseQuery.mockReturnValue({
      data: [seg({ id: "2", usuario_id: "colega", encerrado_em: null })],
      isPending: false,
      isFetching: false,
    } as never);
    expect(useApontamentos("t1", "eu").emAndamento).toBeNull();
  });

  it("does not report loading while data exists and a refetch is in flight", () => {
    mockUseQuery.mockReturnValue({ data: [], isPending: false, isFetching: true } as never);
    const r = useApontamentos("t1", "eu");
    expect(r.loading).toBe(false);
    expect(r.refreshing).toBe(true);
  });
});

describe("useAprovacaoPublica — loading formula", () => {
  it("does not report loading while the client's aprovação is on screen mid-refetch", () => {
    mockUseQuery.mockReturnValue({
      data: {
        titulo: "x", pecas: [], copy_texto: null, direcao_video: null, formato: null,
        cliente_nome: null, ja_decidida: false, aguardando_aprovacao: true,
      },
      isPending: false,
      isFetching: true,
    } as never);
    expect(useAprovacaoPublica("token-1").loading).toBe(false);
  });

  it("REGRESSION: never reports a non-loading empty state before the FIRST fetch settles", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: true, isFetching: true } as never);
    const { loading, aprovacao } = useAprovacaoPublica("token-1");
    expect(loading).toBe(true);
    expect(aprovacao).toBeNull();
  });
});
