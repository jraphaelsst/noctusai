/**
 * Esteira page — render-level tests through the REAL seed `PipelineBoard`.
 *
 * Mocks `@tanstack/react-query` itself (not the hooks), so the page renders
 * through the real `esteiraPipeline` descriptor, the real board organ and the
 * real card face. Covers: first-load skeleton, the refetch-unmount regression
 * (fleet audit 2026-08-31), the error state, the rich card face (smoke finding
 * 5), the `?cliente=` filter reaching the board query (R9), and the admin-only
 * stage editing (R3).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";

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
  pauta: { id: "pauta-1", titulo: "Lançamento outubro", formato: "reels", data_publicacao: null },
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
    return { data: [], isPending: false, isFetching: false, isError: false, error: null };
  }) as never);
}

function renderEsteira(url = "/esteira") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Esteira />
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
