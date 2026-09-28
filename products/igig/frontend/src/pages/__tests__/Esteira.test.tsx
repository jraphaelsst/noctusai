/**
 * Esteira page — render-level tests through the REAL seed `PipelineBoard`.
 *
 * Mocks `@tanstack/react-query` itself (not the hooks), so the page renders
 * through the real `esteiraPipeline` descriptor, the real board organ and the
 * real card face. Covers: first-load skeleton, the refetch-unmount regression
 * (fleet audit 2026-08-31), the error state, the rich card face (smoke finding
 * 5), the `?cliente=` filter reaching the board query (R9), the admin-only
 * stage editing (R3), and the stage-role picker (achado 11) — migrated from
 * a private `PapeisEtapas` onto the shared `StageRolePanel` organ, now
 * sourced from the seed's stages-only query instead of the whole board.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, useSearchParams } from "react-router-dom";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() },
}));

// The tarefa detail sheet's "Repertório da marca" panel is unrelated to the
// deep-link behaviour under test here and needs its own query-shape wiring
// (an object, not the generic `{data: []}` fallback every other hook below
// gets) — stubbed out exactly like `TarefaDetalhe.test.tsx` does.
vi.mock("@/components/RepertorioSidebar", () => ({ RepertorioSidebar: () => null }));

const { mockUser } = vi.hoisted(() => ({
  mockUser: { current: { id: "usuario-1", user_metadata: {} as Record<string, unknown> } },
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  useAuthStore: () => ({ user: mockUser.current }),
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn();
  const useMutation = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient, keepPreviousData: (p: unknown) => p };
});

import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import Esteira from "../Esteira";
import type { TarefaCard } from "@/hooks/useEsteira";
import { ESTEIRA_BOARD_KEY } from "@/hooks/useEsteira";

const mockUseQuery = vi.mocked(useQuery);
/** The board skeleton's accessible name (dnd-kit adds its own unnamed live region). */
const SKELETON = "Carregando quadro";

const TAREFA: TarefaCard = {
  id: "tarefa-1",
  org_id: "org-1",
  pauta_id: "pauta-1",
  cliente_id: "cliente-1",
  titulo: "Reels de lançamento",
  etapa_id: "st-1",
  responsavel_id: "prof-1",
  prazo: "2020-01-10",
  refacoes: 2,
  observacao_cliente: null,
  created_at: null,
  updated_at: null,
  pauta: {
    id: "pauta-1", titulo: "Lançamento outubro", formato: "reels",
    data_publicacao: null, marca_id: null,
  },
  cliente: { id: "cliente-1", nome: "Padaria Sol" },
  responsavel: { id: "prof-1", nome: "Ana Designer" },
};

const stage = (id: string, label: string, posicao: number, papel: string | null = null) => ({
  id, slug: id, label, cor: "primary" as const, posicao, papel, ativo: true,
});

const BOARD = [
  { etapa: "st-1", stage: stage("st-1", "Aguardando roteiro", 0), total: 1, valorTotal: 0, cards: [TAREFA] },
  { etapa: "st-2", stage: stage("st-2", "Aprovação do cliente", 1, "aprovacao_cliente"), total: 0, valorTotal: 0, cards: [] },
];

/** Route by query key: the board state under test; every other list settled + empty. */
function mockBoardState(state: Record<string, unknown>) {
  mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
    if (opts?.queryKey?.[0] === ESTEIRA_BOARD_KEY) return state;
    // `useTarefaPorId`'s key is `[...ESTEIRA_QUERY_KEY, "tarefa", id]` — a
    // single-entity fallback, so its "nothing yet" shape is `data: undefined`
    // (a real disabled/miss query), never `[]` like the list-returning
    // queries every other unmatched key below stands in for.
    if (opts?.queryKey?.[2] === "tarefa") {
      return { data: undefined, isPending: false, isFetching: false, isError: false, error: null };
    }
    return { data: [], isPending: false, isFetching: false, isError: false, error: null };
  }) as never);
}

/** Surfaces the live `?tarefa=` param via the SAME router context `Esteira`
 * reads/writes, so a test can assert the URL was actually updated — a bare
 * `MemoryRouter` has no `window.location` to inspect. */
function ProbeTarefaParam() {
  const [params] = useSearchParams();
  return <div data-testid="probe-tarefa-param">{params.get("tarefa") ?? "none"}</div>;
}

function renderEsteira(url = "/esteira") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Esteira />
      <ProbeTarefaParam />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.current = { id: "usuario-1", user_metadata: {} };
});

describe("Esteira — states", () => {
  it("shows the skeleton before any data has ever arrived", () => {
    mockBoardState({ data: undefined, isPending: true, isFetching: true, error: null });
    renderEsteira();
    expect(screen.getByRole("status", { name: SKELETON })).toBeInTheDocument();
    expect(screen.queryByText("Reels de lançamento")).not.toBeInTheDocument();
  });

  it("REGRESSION: keeps the cards mounted during a background refetch", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: true, error: null });
    renderEsteira();
    expect(screen.getByText("Reels de lançamento")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: SKELETON })).not.toBeInTheDocument();
  });

  it("shows the error and no skeleton once the board query fails", () => {
    mockBoardState({
      data: undefined, isPending: false, isFetching: false, error: new Error("Falha ao carregar"),
    });
    renderEsteira();
    expect(screen.getByRole("alert")).toHaveTextContent("Falha ao carregar");
    expect(screen.queryByRole("status", { name: SKELETON })).not.toBeInTheDocument();
  });

  it("renders every stage as a column, empty ones included", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira();
    expect(screen.getByText("Aprovação do cliente")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma tarefa")).toBeInTheDocument();
  });
});

describe("Esteira — card face (smoke finding 5)", () => {
  it("shows cliente, pauta + formato, responsável, overdue prazo and refações", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira();
    const card = screen.getByTestId("tarefa-card");
    expect(card).toHaveTextContent("Padaria Sol");
    expect(card).toHaveTextContent("Lançamento outubro");
    expect(card).toHaveTextContent("reels");
    expect(card).toHaveTextContent("Ana Designer");
    expect(card).toHaveTextContent("2 refações");
    expect(screen.getByTitle("Prazo vencido")).toHaveClass("text-destructive");
  });
});

describe("Esteira — cliente filter (R9)", () => {
  it("passes ?cliente= to the board query as cliente_id", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira("/esteira?cliente=cliente-1");
    const boardKeys = mockUseQuery.mock.calls
      .map(([opts]) => (opts as { queryKey: unknown[] }).queryKey)
      .filter((k) => k[0] === ESTEIRA_BOARD_KEY);
    expect(boardKeys.length).toBeGreaterThan(0);
    expect(boardKeys.every((k) => JSON.stringify(k[1]) === JSON.stringify({ cliente_id: "cliente-1" }))).toBe(true);
  });

  it("queries the whole board without a filter", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira();
    const boardKey = mockUseQuery.mock.calls
      .map(([opts]) => (opts as { queryKey: unknown[] }).queryKey)
      .find((k) => k[0] === ESTEIRA_BOARD_KEY);
    expect(boardKey?.[1]).toEqual({});
  });
});

describe("Esteira — stage editing is for org admins (R3)", () => {
  it("hides the stage editor from a member", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "member" } };
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira();
    expect(screen.queryByText("Configurar etapas")).not.toBeInTheDocument();
  });

  it("offers the stage editor to an admin", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "admin" } };
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira();
    expect(screen.getByText("Configurar etapas")).toBeInTheDocument();
  });
});

/** Stages-only query key the shared `StageRolePanel` now reads (see
 * `EsteiraBoard.tsx`'s `useStages` comment) — distinct from `ESTEIRA_BOARD_KEY`. */
const ESTEIRA_STAGES_KEY = `${ESTEIRA_BOARD_KEY}-stages`;

/** Routes the board query AND the stages-only query independently — the
 * migrated picker (achado 11) reads the latter, everything else on the page
 * still reads the former. */
function mockBoardAndStages(board: Record<string, unknown>, stages: Record<string, unknown>) {
  mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
    if (opts?.queryKey?.[0] === ESTEIRA_BOARD_KEY) return board;
    if (opts?.queryKey?.[0] === ESTEIRA_STAGES_KEY) return stages;
    return { data: [], isPending: false, isFetching: false, isError: false, error: null };
  }) as never);
}

describe("Esteira — stage role picker, migrated onto StageRolePanel (achado 11)", () => {
  const STAGES = BOARD.map((c) => c.stage);

  it("hides the papéis panel from a member (same gate as the stage editor)", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "member" } };
    mockBoardAndStages(
      { data: BOARD, isPending: false, isFetching: false, error: null },
      { data: STAGES, isPending: false, isFetching: false, error: null },
    );
    renderEsteira();
    expect(screen.queryByTestId("stage-role-panel")).not.toBeInTheDocument();
  });

  it("offers the papéis panel to an admin, pre-selected to the aprovação-do-cliente holder", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "admin" } };
    mockBoardAndStages(
      { data: BOARD, isPending: false, isFetching: false, error: null },
      { data: STAGES, isPending: false, isFetching: false, error: null },
    );
    renderEsteira();

    const painel = screen.getByTestId("stage-role-panel");
    fireEvent.click(within(painel).getByText("Papéis das etapas"));
    const select = screen.getByLabelText(
      "Etapa com o papel Aprovação do cliente",
    ) as HTMLSelectElement;
    expect(painel).toContainElement(select);
    expect(select.value).toBe("st-2");
  });

  it("sources its options from the stages-only query, excluding inactive stages (parity with the old board-derived list)", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "admin" } };
    const arquivada = stage("st-3", "Arquivado", 2);
    mockBoardAndStages(
      { data: BOARD, isPending: false, isFetching: false, error: null },
      { data: [...STAGES, { ...arquivada, ativo: false }], isPending: false, isFetching: false, error: null },
    );
    renderEsteira();

    const painel = screen.getByTestId("stage-role-panel");
    fireEvent.click(within(painel).getByText("Papéis das etapas"));
    // Two selects (one per role), each listing every ACTIVE stage as an
    // option — "Aguardando roteiro" is expected in both, "Arquivado" in none.
    expect(within(painel).queryByText("Arquivado")).not.toBeInTheDocument();
    expect(within(painel).getAllByText("Aguardando roteiro").length).toBe(2);
  });
});

describe("Esteira — ?tarefa=<id> deep link (tech-lead addendum, 2026-09)", () => {
  it("opens the tarefa's detail sheet when the id is on the current board", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira("/esteira?tarefa=tarefa-1");
    expect(screen.getByTestId("tarefa-detalhe")).toBeInTheDocument();
    expect(screen.getAllByText("Reels de lançamento").length).toBeGreaterThan(0);
  });

  it("shows a toast and never opens a sheet for an id not on the board", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira("/esteira?tarefa=nao-existe");
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("não encontrada"));
    expect(screen.queryByTestId("tarefa-detalhe")).not.toBeInTheDocument();
  });

  it("does not toast while the board is still loading — waits for real data", () => {
    mockBoardState({ data: undefined, isPending: true, isFetching: true, error: null });
    renderEsteira("/esteira?tarefa=tarefa-1");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("opens the tarefa via a direct fetch when it belongs to a cliente OUTSIDE the current filter", () => {
    /** achado: `?tarefa=<id>` used to be resolvable only against the loaded
     * (possibly cliente-filtered) board — a tarefa genuinely belonging to a
     * different cliente than `?cliente=` read as "não encontrada". */
    const foraDoFiltro: TarefaCard = {
      ...TAREFA, id: "tarefa-2", cliente_id: "cliente-2", titulo: "Post de outro cliente",
    };
    mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
      if (opts?.queryKey?.[0] === ESTEIRA_BOARD_KEY) {
        return { data: BOARD, isPending: false, isFetching: false, isError: false, error: null };
      }
      if (opts?.queryKey?.[2] === "tarefa") {
        return { data: foraDoFiltro, isPending: false, isFetching: false, isError: false, error: null };
      }
      return { data: [], isPending: false, isFetching: false, isError: false, error: null };
    }) as never);

    renderEsteira("/esteira?cliente=cliente-1&tarefa=tarefa-2");

    expect(screen.getByTestId("tarefa-detalhe")).toBeInTheDocument();
    expect(screen.getAllByText("Post de outro cliente").length).toBeGreaterThan(0);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("does not toast while the fallback fetch is still resolving — an in-flight fetch is not a miss", () => {
    mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
      if (opts?.queryKey?.[0] === ESTEIRA_BOARD_KEY) {
        return { data: BOARD, isPending: false, isFetching: false, isError: false, error: null };
      }
      if (opts?.queryKey?.[2] === "tarefa") {
        return { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
      }
      return { data: [], isPending: false, isFetching: false, isError: false, error: null };
    }) as never);

    renderEsteira("/esteira?cliente=cliente-1&tarefa=tarefa-2");

    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.queryByTestId("tarefa-detalhe")).not.toBeInTheDocument();
  });

  it("closing the deep-linked sheet clears the ?tarefa= param", () => {
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderEsteira("/esteira?tarefa=tarefa-1");
    expect(screen.getByTestId("probe-tarefa-param")).toHaveTextContent("tarefa-1");

    const fechar = screen.getAllByRole("button", { name: /fechar/i })[0];
    fireEvent.click(fechar);

    expect(screen.getByTestId("probe-tarefa-param")).toHaveTextContent("none");
  });
});
