/**
 * Painel.test.tsx — the dashboard capability lock (`capacidades.dashboard`),
 * loading/error/refreshing states, the honest "sem dados de faturamento"
 * note, the org filter being platform-admin-only, and the date-range
 * filters reaching `usePainel`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseCapacidades = vi.fn();
const mockUsePainel = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    usePainel: (...a: any[]) => mockUsePainel(...a),
  };
});

function capacidades(overrides: Partial<any> = {}) {
  return {
    pode_criar_lote: false,
    pode_ver_veredito: false,
    pode_gerir_pool: false,
    pode_aprovar_regras: false,
    pode_ativar_guia: false,
    dashboard: "org",
    modelo_configurado: false,
    economico_disponivel: false,
    economico_bloqueado_motivo: "sem_modelo",
    tipos_edicao_ativos: [],
    limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
    ...overrides,
  };
}

function painel(overrides: Partial<any> = {}) {
  return {
    periodo: { desde: "2026-08-17", ate: "2026-09-16" },
    escopo: "organizacao",
    pipeline: { pontos: [{ data: "2026-09-16", estado: "aprovada", total: 3 }] },
    fila: {
      escopo: "plataforma",
      jobs: { pending: 0, running: 0, completed: 5, failed: 0, dead_letter: 0 },
      travados: 0,
      fotos_por_estado: { aprovada: 3 },
    },
    atividade: {
      lotes_criados: 1,
      fotos_enviadas: 3,
      decisoes: { aprovar: 3, rejeitar: 0 },
      usuarios_ativos: 1,
      serie_diaria: [{ data: "2026-09-16", lotes: 1, fotos: 3, decisoes: 3 }],
    },
    aprendizado: {
      taxa_aprovacao: 1.0,
      veredito_ia: { aprovar: 3, rejeitar: 0 },
      acerto_ia_pct: 100.0,
      regras: { aprovadas: 0, pendentes: 0 },
    },
    custos: {
      moeda_base: "BRL",
      por_categoria: [{ categoria: "openai_edit", total_brl: 4.5 }],
      total_brl: 4.5,
      fx_pendentes: 0,
      receita: { disponivel: false, total_brl: 0, nota: "sem dados de faturamento" },
      margem_brl: -4.5,
    },
    ...overrides,
  };
}

function painelHook(overrides: Partial<any> = {}) {
  return {
    painel: painel(),
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Painel } = await import("./Painel");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Painel))),
    rtl,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCapacidades.mockReturnValue({ capacidades: capacidades(), showSkeleton: false });
  mockUsePainel.mockReturnValue(painelHook());
});

describe("Painel — access + states", () => {
  it("locks the page for a corretor (capacidades.dashboard === null) and never calls usePainel", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: null }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("painel-restrito")).toBeTruthy();
    expect(mockUsePainel).not.toHaveBeenCalled();
  });

  it("shows the skeleton while capacidades is pending", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("painel-loading")).toBeTruthy();
    expect(mockUsePainel).not.toHaveBeenCalled();
  });

  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUsePainel.mockReturnValue(painelHook({ painel: undefined, error: new Error("x"), refetch }));
    const { getByText, rtl } = await renderPage();
    rtl.fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("keeps the dashboard mounted while refreshing", async () => {
    mockUsePainel.mockReturnValue(painelHook({ isRefreshing: true }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("painel-atualizando")).toBeTruthy();
    expect(getByTestId("edicao-fotos-painel")).toBeTruthy();
  });
});

describe("Painel — org scope", () => {
  it("shows the org filter for a platform admin", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "platform" }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("painel-org-filter")).toBeTruthy();
  });

  it("hides the org filter for an agency admin", async () => {
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("painel-org-filter")).toBeNull();
  });
});

describe("Painel — content", () => {
  it("renders the honest 'sem dados de faturamento' note, never a fabricated revenue", async () => {
    const { getByTestId, rtl } = await renderPage();
    const card = getByTestId("painel-sem-faturamento");
    expect(card).toBeTruthy();
    expect(rtl.within(card).getByText("sem dados de faturamento")).toBeTruthy();
  });

  it("surfaces stuck jobs when fila.travados > 0", async () => {
    mockUsePainel.mockReturnValue(
      painelHook({ painel: painel({ fila: { ...painel().fila, travados: 2 } }) })
    );
    const { getByTestId } = await renderPage();
    expect(getByTestId("painel-travados").textContent).toContain("2");
  });

  it("does not render the stuck-jobs note when travados is 0", async () => {
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("painel-travados")).toBeNull();
  });
});

describe("Painel — date range filter", () => {
  it("passes the desde/ate inputs to usePainel", async () => {
    const { getByLabelText, rtl } = await renderPage();
    rtl.fireEvent.change(getByLabelText("De"), { target: { value: "2026-01-01" } });
    await rtl.waitFor(() => {
      const calls = mockUsePainel.mock.calls;
      const lastCall = calls[calls.length - 1]?.[0];
      expect(lastCall?.desde).toBe("2026-01-01");
    });
  });
});
