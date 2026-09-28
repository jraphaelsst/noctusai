/**
 * Dashboard — the two-signal loading regression (live smoke finding: the red
 * "Nenhum profissional com custo/hora cadastrado" banner and "R$ 0,00"
 * receita used to render WHILE their queries were still on the first fetch),
 * the competência-scoped DRE (achado #6/plat#5 — it used to sum ALL TIME),
 * server-count clientes ativos (achado #7/plat#5 — it used to filter the
 * 50-capped list), and the new Comercial KPIs (achado #21).
 *
 * Mocks `@tanstack/react-query`'s `useQuery` directly (not the product hooks)
 * so the page renders through its REAL hook wiring — the same approach
 * `Esteira.test.tsx` uses — routed by `queryKey`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn();
  const useMutation = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient, keepPreviousData: (p: unknown) => p };
});

import { useQuery } from "@tanstack/react-query";
import Dashboard from "../Dashboard";
import { CUSTOS_QUERY_KEY } from "@/hooks/useCustos";
import { COMERCIAL_BOARD_KEY } from "@/lib/pipelines";
import { ESTEIRA_BOARD_KEY } from "@/hooks/useEsteira";

const mockUseQuery = vi.mocked(useQuery);

const LOADING = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
const VAZIO = { data: [], isPending: false, isFetching: false, isError: false, error: null };

interface Estado {
  profissionais?: unknown;
  dre?: unknown;
  clientesAtivos?: unknown;
  clientesInadimplentes?: unknown;
  comercial?: unknown;
  inadimplentes?: unknown;
}

/** Routes every `useQuery` call by its key; anything unspecified settles
 * empty so an unrelated query never leaves the page stuck loading. */
function mockEstado(estado: Estado) {
  mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
    const chave = opts?.queryKey ?? [];
    if (chave[0] === COMERCIAL_BOARD_KEY) return estado.comercial ?? VAZIO;
    if (chave[0] === ESTEIRA_BOARD_KEY) return VAZIO;
    if (chave[1] === "financeiro" && chave[2] === "dre") return estado.dre ?? VAZIO;
    if (chave[1] === "financeiro" && chave[2] === "inadimplentes") return estado.inadimplentes ?? VAZIO;
    if (chave[1] === CUSTOS_QUERY_KEY[1] && chave[2] === "profissionais") {
      return estado.profissionais ?? VAZIO;
    }
    if (chave[1] === "clientes" && chave[3] === "ativo") return estado.clientesAtivos ?? VAZIO;
    if (chave[1] === "clientes" && chave[3] === "inadimplente") return estado.clientesInadimplentes ?? VAZIO;
    return VAZIO;
  }) as never);
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Dashboard — two-signal loading (no lying banner / no lying R$ 0,00)", () => {
  it("shows neither the cost-alert banner nor a confident receita while still loading", () => {
    mockEstado({ profissionais: LOADING, dre: LOADING });
    renderDashboard();
    expect(screen.queryByText(/Nenhum profissional com custo\/hora/)).not.toBeInTheDocument();
    expect(screen.getByText("Receita no mês").closest("a")).toHaveTextContent("—");
    expect(screen.getByText("Margem no mês").closest("a")).toHaveTextContent("—");
  });

  it("shows the banner once profissionais has actually loaded and is empty", () => {
    mockEstado({ profissionais: { data: [], isPending: false, isFetching: false, isError: false, error: null } });
    renderDashboard();
    expect(screen.getByText(/Nenhum profissional com custo\/hora/)).toBeInTheDocument();
  });

  it("never shows the banner once profissionais has loaded WITH rates set", () => {
    mockEstado({
      profissionais: {
        data: [{ id: "p1", custo_hora_indefinido: false }],
        isPending: false, isFetching: false, isError: false, error: null,
      },
    });
    renderDashboard();
    expect(screen.queryByText(/Nenhum profissional com custo\/hora/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sem custo\/hora/)).not.toBeInTheDocument();
  });
});

describe("Dashboard — Receita/Margem no mês (achado #6/plat#5)", () => {
  it("passes a competência to the DRE query — not an all-time sum", () => {
    mockEstado({});
    renderDashboard();
    const dreCalls = mockUseQuery.mock.calls
      .map(([opts]) => (opts as { queryKey: unknown[] }).queryKey)
      .filter((k) => k[1] === "financeiro" && k[2] === "dre");
    expect(dreCalls).toHaveLength(1);
    expect(dreCalls[0][3]).toMatch(/^\d{4}-\d{2}$/);
  });

  it("also scopes COST to the same competência — never the DRE screen's full-history default", () => {
    // Finding: this card compared a month's revenue against ALL-TIME cost
    // (the M6 DRE screen's own documented behaviour, wrong here). The
    // Dashboard's DRE query must request `custoPorCompetencia`.
    mockEstado({});
    renderDashboard();
    const dreCalls = mockUseQuery.mock.calls
      .map(([opts]) => (opts as { queryKey: unknown[] }).queryKey)
      .filter((k) => k[1] === "financeiro" && k[2] === "dre");
    expect(dreCalls[0][4]).toBe(true);
  });

  it("sums only the loaded competência's DRE rows", () => {
    mockEstado({
      profissionais: { data: [{ id: "p1", custo_hora_indefinido: false }], isPending: false, isFetching: false, isError: false, error: null },
      dre: {
        data: [{ cliente_id: "c1", cliente_nome: "Padaria Sol", receita: 5000, custo: 2000, margem: 3000, margem_percentual: 60, alertas: [] }],
        isPending: false, isFetching: false, isError: false, error: null,
      },
    });
    renderDashboard();
    expect(screen.getByText(/R\$\s*5\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/R\$\s*3\.000,00/)).toBeInTheDocument();
  });
});

describe("Dashboard — Clientes ativos (achado #7/plat#5)", () => {
  it("reads the server COUNT, not the 50-capped list length", () => {
    mockEstado({
      clientesAtivos: { data: { itens: new Array(50).fill({ id: "x" }), total: 137 }, isPending: false, isFetching: false, isError: false, error: null },
    });
    renderDashboard();
    expect(screen.getByText("137")).toBeInTheDocument();
  });
});

describe("Dashboard — Comercial KPIs (achado #21)", () => {
  const COMPETENCIA_ATUAL = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit",
  }).format(new Date());

  it("counts open negócios, sums their valor, and counts this month's ganhos", () => {
    mockEstado({
      comercial: {
        data: [
          {
            etapa: "e1", stage: { id: "e1", label: "Leads" }, total: 2, valorTotal: 0,
            cards: [
              { id: "n1", status: "aberto", valor_estimado: 1000, ganho_em: null },
              { id: "n2", status: "aberto", valor_estimado: 2500, ganho_em: null },
            ],
          },
          {
            etapa: "e2", stage: { id: "e2", label: "Fechado", papel: "fechado" }, total: 1, valorTotal: 0,
            cards: [{ id: "n3", status: "ganho", valor_estimado: 800, ganho_em: `${COMPETENCIA_ATUAL}-15T10:00:00Z` }],
          },
        ],
        isPending: false, isFetching: false, isError: false, error: null,
      },
    });
    renderDashboard();
    expect(screen.getByText("2")).toBeInTheDocument(); // negócios abertos
    expect(screen.getByText(/R\$\s*3\.500,00/)).toBeInTheDocument(); // valor em negociação
    expect(screen.getByText("1")).toBeInTheDocument(); // ganhos no mês
  });

  it("does not count a ganho from a previous month", () => {
    mockEstado({
      comercial: {
        data: [
          {
            etapa: "e2", stage: { id: "e2", label: "Fechado", papel: "fechado" }, total: 1, valorTotal: 0,
            cards: [{ id: "n3", status: "ganho", valor_estimado: 800, ganho_em: "2020-01-15T10:00:00Z" }],
          },
        ],
        isPending: false, isFetching: false, isError: false, error: null,
      },
    });
    renderDashboard();
    const rotulo = screen.getByText("Ganhos no mês");
    expect(rotulo.closest("a")).toHaveTextContent("0");
  });
});

describe("Dashboard — Inadimplência two-signal loading (leftovers item 13)", () => {
  it("shows a skeleton while still loading, never a confident 'Nenhuma fatura vencida'", () => {
    mockEstado({ inadimplentes: LOADING });
    renderDashboard();
    expect(screen.queryByText("Nenhuma fatura vencida.")).not.toBeInTheDocument();
  });

  it("shows the server's error instead of a confident empty state", () => {
    mockEstado({
      inadimplentes: { data: undefined, isPending: false, isFetching: false, isError: true, error: new Error("Falha ao carregar") },
    });
    renderDashboard();
    expect(screen.getByRole("alert")).toHaveTextContent("Falha ao carregar");
    expect(screen.queryByText("Nenhuma fatura vencida.")).not.toBeInTheDocument();
  });

  it("shows the empty state only once loaded, with no error", () => {
    mockEstado({ inadimplentes: VAZIO });
    renderDashboard();
    expect(screen.getByText("Nenhuma fatura vencida.")).toBeInTheDocument();
  });
});
