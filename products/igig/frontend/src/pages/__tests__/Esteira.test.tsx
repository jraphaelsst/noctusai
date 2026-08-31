/**
 * Esteira — render-level regression test for the refetch-unmount bug
 * (fleet audit, 2026-08-31): "edit one field and a whole block of UI
 * vanishes while the layout collapses, then returns."
 *
 * Unlike a test that mocks `@/hooks/useEsteira` wholesale, this mocks
 * `@tanstack/react-query` ITSELF (mirrors `useEsteira.test.ts`), so the
 * page renders through the REAL `useQuadro()` — the `loading` formula under
 * test actually runs. Reverting `useQuadro`'s `isPending && !query.data`
 * back to `isPending || isFetching` makes the second test below fail.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn();
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({
    ...opts,
    mutate: vi.fn(),
    isPending: false,
  }));
  const useQueryClient = vi.fn(() => ({
    cancelQueries: vi.fn(),
    getQueryData: vi.fn(),
    setQueryData: vi.fn(),
    invalidateQueries: vi.fn(),
  }));
  return { useQuery, useMutation, useQueryClient };
});

import { useQuery } from "@tanstack/react-query";
import Esteira from "../Esteira";
import type { Quadro } from "@/hooks/useEsteira";

const mockUseQuery = vi.mocked(useQuery);

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

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Esteira — first load", () => {
  it("shows the skeleton before any data has ever arrived", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    render(<Esteira />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Reels de lançamento")).not.toBeInTheDocument();
  });
});

describe("Esteira — refetch-unmount regression", () => {
  it("keeps the board mounted (cards stay in the DOM) during a background refetch", () => {
    // isPending false + isFetching true + data present — exactly what
    // TanStack v5 reports right after `useMoverTarefa`/`useIniciarTimer`/
    // etc. invalidate the quadro. This must NOT collapse the board.
    mockUseQuery.mockReturnValue({
      data: QUADRO,
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    render(<Esteira />);

    expect(screen.getByText("Reels de lançamento")).toBeInTheDocument();
    // No loading region should be announced once real content is on screen.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("still shows the settled board once the refetch completes", () => {
    mockUseQuery.mockReturnValue({
      data: QUADRO,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    } as never);

    render(<Esteira />);

    expect(screen.getByText("Reels de lançamento")).toBeInTheDocument();
  });
});

describe("Esteira — error state", () => {
  it("shows the error message and no skeleton once the query errors out", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: true,
      error: new Error("boom"),
    } as never);

    render(<Esteira />);

    expect(screen.getByText("Não foi possível carregar a esteira.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
