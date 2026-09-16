/**
 * Configuracoes.test.tsx — the role-gate inference (`dashboardScope !==
 * null`, documented in the page header), the model-missing banner ("blocks
 * batch creation" per the brief), and the loading/error/success states.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseConfiguracoes = vi.fn();
const mockUseModelos = vi.fn();
const mockAtualizar = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useConfiguracoes: (...a: any[]) => mockUseConfiguracoes(...a),
    useModelos: (...a: any[]) => mockUseModelos(...a),
    useAtualizarConfiguracoes: () => ({ mutateAsync: mockAtualizar, isPending: false }),
  };
});

const CONFIG = {
  tipos_edicao_ativos: ["cor_luz", "ceu"],
  modelo_editor_imagem: "gpt-image-2",
  velocidade_padrao: "urgente" as const,
};

function capacidades(overrides: Partial<any> = {}) {
  return {
    pode_criar_lote: true,
    pode_ver_veredito: false,
    pode_gerir_pool: false,
    pode_aprovar_regras: false,
    pode_ativar_guia: false,
    dashboard: "org",
    modelo_configurado: true,
    economico_disponivel: false,
    economico_bloqueado_motivo: "modelo_sem_batch",
    tipos_edicao_ativos: ["cor_luz"],
    limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Configuracoes } = await import("./Configuracoes");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Configuracoes))),
    fireEvent: rtl.fireEvent,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseModelos.mockReturnValue({ modelos: [], showSkeleton: false, error: null, refetch: vi.fn() });
});

describe("Configuracoes — loading", () => {
  it("shows the form skeleton while configuracoes is pending", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: undefined, showSkeleton: true, error: null, refetch: vi.fn() });
    const { getByTestId } = await renderPage();
    expect(getByTestId("configuracoes-loading")).toBeTruthy();
  });
});

describe("Configuracoes — error", () => {
  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseCapacidades.mockReturnValue({ capacidades: undefined });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: undefined, showSkeleton: false, error: new Error("x"), refetch });
    const { getByText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe("Configuracoes — modelo ausente banner", () => {
  it("shows the blocking banner when modelo_configurado is false, regardless of role", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ modelo_configurado: false, dashboard: null }) });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: CONFIG, showSkeleton: false, error: null, refetch: vi.fn() });
    const { getByText } = await renderPage();
    expect(
      getByText(
        "Nenhum modelo de edição de imagem configurado — a criação de lotes está bloqueada até um modelo ser escolhido abaixo.",
      ),
    ).toBeTruthy();
  });
});

describe("Configuracoes — corretor (read-only)", () => {
  it("renders the read-only summary, not the editable form, when dashboard is null", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: null }) });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: CONFIG, showSkeleton: false, error: null, refetch: vi.fn() });
    const { getByTestId, queryByText } = await renderPage();
    expect(getByTestId("configuracoes-somente-leitura")).toBeTruthy();
    expect(queryByText("Salvar")).toBeNull();
  });
});

describe("Configuracoes — admin (editable)", () => {
  it("renders the editable form and saves the draft on Salvar", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "org" }) });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: CONFIG, showSkeleton: false, error: null, refetch: vi.fn() });
    mockAtualizar.mockResolvedValue(undefined);

    const { getByText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Salvar"));

    await vi.waitFor(() => expect(mockAtualizar).toHaveBeenCalledWith(CONFIG));
  });

  it("shows the empty-catalog message instead of a picker when GET /modelos returns nothing", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "org" }) });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: CONFIG, showSkeleton: false, error: null, refetch: vi.fn() });
    mockUseModelos.mockReturnValue({ modelos: [], showSkeleton: false, error: null, refetch: vi.fn() });

    const { getByTestId } = await renderPage();
    expect(getByTestId("modelos-vazio")).toBeTruthy();
  });
});
