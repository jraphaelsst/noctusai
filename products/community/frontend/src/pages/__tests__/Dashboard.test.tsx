/**
 * Dashboard render tests — ninho-vazio CONTRACT.md §Cashflow + dashboard
 * (`GET /api/dashboard`) and the two-signal loading rule
 * (KB § PATTERNS/frontend/lying-loading-state.md).
 *
 * The fixture is the contract's own response shape; every assertion reads a
 * value the page must take verbatim from it (the page computes no KPI).
 */
import React from "react";
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";

const mockGet = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    coreApi: api,
    supabase: {},
    appConfig: {},
    useAuthStore: () => ({ user: null }),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    default: { api },
  };
});

beforeAll(() => {
  // jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one to mount.
  class StubResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = StubResizeObserver as unknown as typeof ResizeObserver;
});

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function neverResolves<T>(): Promise<T> {
  return new Promise<T>(() => {});
}

/** Contract-shaped payload (CONTRACT.md §Cashflow + dashboard). */
const DASHBOARD = {
  kpis: {
    membros_total: 57,
    membros_ativos: 42,
    por_plano: [
      { plano_id: "p-0", nome: "Gratuito", nivel_grupoterapia: "nenhum", membros: 30 },
      { plano_id: "p-1", nome: "Ouvinte", nivel_grupoterapia: "ouvir", membros: 8 },
      { plano_id: "p-2", nome: "Premium", nivel_grupoterapia: "falar", membros: 4 },
    ],
    mrr_centavos: 16400,
    arpu_centavos: 1367,
    em_carencia: 3,
    novos_mes: 9,
    cancelamentos_mes: 2,
    churn_mes_pct: 12.5,
    receita_mes_centavos: 15700,
    saldo_mes_centavos: 9950,
    conversao_pago_pct: 28.6,
  },
  series: {
    mensal: [
      { mes: "2026-08", entradas_centavos: 10000, saidas_centavos: 3000, novos_membros: 20, cancelamentos: 1, mrr_centavos: 9800 },
      { mes: "2026-09", entradas_centavos: 15700, saidas_centavos: 5750, novos_membros: 9, cancelamentos: 2, mrr_centavos: 16400 },
    ],
    origem_membros: [
      { origem: "cadastro", membros: 40 },
      { origem: "checkout", membros: 17 },
    ],
    status_membros: [
      { status: "ativo", membros: 39 },
      { status: "atrasado", membros: 3 },
      { status: "cancelado", membros: 15 },
    ],
    grupoterapia: [
      { sessao_id: "s-1", titulo: "Roda de conversa", inicio: "2026-10-02T22:00:00Z", vagas_fala: 8, reservas: 5 },
    ],
  },
  gerado_em: "2026-09-28T19:00:00Z",
};

const ZERADO = {
  kpis: {
    ...DASHBOARD.kpis,
    membros_total: 0,
    membros_ativos: 0,
    por_plano: [],
    mrr_centavos: 0,
    arpu_centavos: 0,
    em_carencia: 0,
    novos_mes: 0,
    cancelamentos_mes: 0,
    churn_mes_pct: 0,
    receita_mes_centavos: 0,
    saldo_mes_centavos: 0,
    conversao_pago_pct: 0,
  },
  series: {
    mensal: [{ mes: "2026-09", entradas_centavos: 0, saidas_centavos: 0, novos_membros: 0, cancelamentos: 0, mrr_centavos: 0 }],
    origem_membros: [],
    status_membros: [],
    grupoterapia: [],
  },
  gerado_em: "2026-09-28T19:00:00Z",
};

function tile(label: string): HTMLElement {
  // StatTile's frame is the `p-5` card; a chart card may share the label ("MRR").
  const el = screen
    .getAllByText(label)
    .map((n) => n.closest("div.p-5"))
    .find(Boolean);
  if (!el) throw new Error(`tile ${label} not found`);
  return el as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Dashboard", () => {
  it("renders every KPI straight from the contract payload (centavos → BRL)", async () => {
    mockGet.mockResolvedValue(DASHBOARD);
    const Dashboard = (await import("../Dashboard")).default;
    renderPage(<Dashboard />);

    await waitFor(() => expect(within(tile("Membros ativos")).getByText("42")).toBeInTheDocument());
    expect(mockGet).toHaveBeenCalledWith("/api/dashboard", { meses: 12 });
    expect(within(tile("Membros ativos")).getByText("de 57 no total")).toBeInTheDocument();
    expect(within(tile("MRR")).getByText(/164,00/)).toBeInTheDocument();
    expect(within(tile("ARPU")).getByText(/13,67/)).toBeInTheDocument();
    expect(within(tile("Em carência")).getByText("3")).toBeInTheDocument();
    expect(within(tile("Churn do mês")).getByText("12,5%")).toBeInTheDocument();
    expect(within(tile("Churn do mês")).getByText("9 novos · 2 cancelamentos")).toBeInTheDocument();
    expect(within(tile("Receita do mês")).getByText(/157,00/)).toBeInTheDocument();
    expect(within(tile("Saldo do mês")).getByText(/99,50/)).toBeInTheDocument();
    expect(within(tile("Conversão pago")).getByText("28,6%")).toBeInTheDocument();

    for (const titulo of [
      "Entradas × saídas",
      "Novos × cancelamentos",
      "Membros por plano",
      "Membros por origem",
      "Membros por status",
      "Ocupação da grupoterapia",
    ]) {
      expect(screen.getByText(titulo)).toBeInTheDocument();
    }
    // Real data → no chart card falls into its empty state.
    expect(screen.queryByText("Nenhum lançamento no período.")).not.toBeInTheDocument();
    expect(screen.queryByText("Nenhuma sessão de grupoterapia agendada ou realizada.")).not.toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Carregando" })).not.toBeInTheDocument();
  });

  it("shows skeletons on first load (isPending && !data), never a zero", async () => {
    mockGet.mockReturnValue(neverResolves());
    const Dashboard = (await import("../Dashboard")).default;
    renderPage(<Dashboard />);

    expect(screen.getAllByRole("status", { name: "Carregando" }).length).toBeGreaterThan(0);
    expect(within(tile("MRR")).queryByText(/R\$/)).not.toBeInTheDocument();
    expect(screen.queryByText("Nenhum lançamento no período.")).not.toBeInTheDocument();
  });

  it("keeps the previous numbers on screen while a new window refetches (no lying loading state)", async () => {
    mockGet.mockResolvedValueOnce(DASHBOARD);
    const Dashboard = (await import("../Dashboard")).default;
    renderPage(<Dashboard />);
    await waitFor(() => expect(within(tile("Membros ativos")).getByText("42")).toBeInTheDocument());

    mockGet.mockReturnValue(neverResolves());
    fireEvent.change(screen.getByLabelText("Período do dashboard"), { target: { value: "24" } });

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/api/dashboard", { meses: 24 }));
    expect(screen.getByText(/Atualizando…/)).toBeInTheDocument();
    // Data exists → it stays mounted: no skeleton, no empty state.
    expect(within(tile("Membros ativos")).getByText("42")).toBeInTheDocument();
    expect(within(tile("MRR")).getByText(/164,00/)).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Carregando" })).not.toBeInTheDocument();
    expect(screen.queryByText("Nenhum lançamento no período.")).not.toBeInTheDocument();
  });

  it("shows empty states only when the settled payload really has no activity", async () => {
    mockGet.mockResolvedValue(ZERADO);
    const Dashboard = (await import("../Dashboard")).default;
    renderPage(<Dashboard />);

    await waitFor(() => expect(screen.getByText("Nenhum lançamento no período.")).toBeInTheDocument());
    expect(screen.getByText("Nenhum membro em plano ainda.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma sessão de grupoterapia agendada ou realizada.")).toBeInTheDocument();
    expect(within(tile("Membros ativos")).getByText("0")).toBeInTheDocument();
  });

  it("renders the backend's error detail when the first load fails", async () => {
    mockGet.mockRejectedValue(new ApiError(403, "Área restrita à equipe."));
    const Dashboard = (await import("../Dashboard")).default;
    renderPage(<Dashboard />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Área restrita à equipe."));
  });

  it("labels contract months in pt-BR", async () => {
    const { formatMes } = await import("../Dashboard");
    expect(formatMes("2026-09")).toBe("Set/26");
    expect(formatMes("2027-01")).toBe("Jan/27");
    expect(formatMes("lixo")).toBe("lixo");
  });
});
