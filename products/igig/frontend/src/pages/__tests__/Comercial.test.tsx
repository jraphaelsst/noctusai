/**
 * Comercial page — render-level tests through the REAL seed `PipelineBoard`.
 *
 * Mocks `@tanstack/react-query` itself (not the hooks), same approach as
 * `Esteira.test.tsx`. Covers the "Papéis das etapas" panel (comercial achado
 * #14) — admin-only, mirroring the seed's own "Configurar etapas" gate which
 * already renders correctly for admins (confirmed here, not re-fixed).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
  // `NegocioCardDialog` (unconditionally mounted, `negocio={null}` while no
  // card is open) runs the seed card hub's `useCardHubGeral`, which calls
  // `useInfiniteQuery` for the activity timeline regardless of the id.
  const useInfiniteQuery = vi.fn(() => ({
    data: undefined, isPending: false, isFetching: false, error: null,
    fetchNextPage: vi.fn(), hasNextPage: false,
  }));
  return { useQuery, useMutation, useQueryClient, useInfiniteQuery, keepPreviousData: (p: unknown) => p };
});

import { useQuery } from "@tanstack/react-query";
import Comercial from "../Comercial";
import { COMERCIAL_BOARD_KEY } from "@/lib/pipelines";
import type { Negocio } from "@/types/crm";

const mockUseQuery = vi.mocked(useQuery);

const stage = (id: string, label: string, posicao: number, papel: string | null = null) => ({
  id, slug: id, label, cor: "primary" as const, posicao, papel, ativo: true,
});

const NEGOCIO: Negocio = {
  id: "n1", org_id: "org", lead_id: "l1", titulo: "Padaria Sol", valor_estimado: 1500, etapa_id: "st-1",
  kanban_pos: 0, responsavel_id: null, status: "aberto", stage_entered_at: null, ganho_em: null,
  perdido_em: null, motivo_perda: null, orcamento_aceito_id: null, cliente_id: null, created_at: "",
  lead: { id: "l1", nome: "Ana", empresa: "Padaria Sol", email: null, telefone: null, instagram: null, origem: "manual", status: "novo" },
  responsavel: null,
  perdido_stage: null,
  dwell_dias: null,
};

const BOARD = [
  { etapa: "st-1", stage: stage("st-1", "Leads", 0), total: 1, valorTotal: 1500, cards: [NEGOCIO] },
  { etapa: "st-2", stage: stage("st-2", "Fechado", 1, "fechado"), total: 0, valorTotal: 0, cards: [] },
];

function mockBoardState(state: Record<string, unknown>) {
  mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
    if (opts?.queryKey?.[0] === COMERCIAL_BOARD_KEY) return state;
    return { data: [], isPending: false, isFetching: false, isError: false, error: null };
  }) as never);
}

function renderComercial(url = "/comercial") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Comercial />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.current = { id: "usuario-1", user_metadata: {} };
});

describe("Comercial — stage role reassignment is for org admins (achado #14)", () => {
  it("hides the seed's stage editor AND the papéis panel from a member", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "member" } };
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderComercial();
    expect(screen.queryByText("Configurar etapas")).not.toBeInTheDocument();
    expect(screen.queryByTestId("stage-role-panel")).not.toBeInTheDocument();
  });

  it("offers BOTH the seed's stage editor and the papéis panel to an admin, pre-selected to the fechado holder", () => {
    mockUser.current = { id: "u", user_metadata: { org_role: "admin" } };
    mockBoardState({ data: BOARD, isPending: false, isFetching: false, error: null });
    renderComercial();
    expect(screen.getByText("Configurar etapas")).toBeInTheDocument();

    const painel = screen.getByTestId("stage-role-panel");
    fireEvent.click(within(painel).getByText("Papéis das etapas"));
    const select = screen.getByLabelText(
      "Etapa com o papel Fechado (exige orçamento aceito)",
    ) as HTMLSelectElement;
    expect(painel).toContainElement(select);
    expect(select.value).toBe("st-2");
  });
});
