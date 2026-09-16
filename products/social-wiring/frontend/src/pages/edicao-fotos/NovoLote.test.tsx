/**
 * NovoLote.test.tsx — the capacidades-gated states (loading / error /
 * permission-denied / model-missing / success), the Econômico lock and its
 * unlock when `capacidades.economico_disponivel` (W4), the org-default speed
 * preselection, and the create → upload → submeter sequence firing in order with
 * the id the CREATE step returned (the timing bug this hook shape exists to
 * avoid — see `hooks.ts`'s comment on `useUploadFotos`).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseConfiguracoes = vi.fn();
const mockCriarLote = vi.fn();
const mockUploadFotos = vi.fn();
const mockLoteVista = vi.fn();
const mockSubmeterLote = vi.fn();
const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useConfiguracoes: () => mockUseConfiguracoes(),
    useCriarLote: () => ({ mutateAsync: mockCriarLote }),
    useUploadFotos: () => ({ mutateAsync: mockUploadFotos }),
    useLoteVista: () => ({ mutateAsync: mockLoteVista }),
    useSubmeterLote: () => ({ mutateAsync: mockSubmeterLote }),
  };
});

const CAPACIDADES_OK = {
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
};

async function renderPage() {
  const React = (await import("react")).default;
  const { default: NovoLote } = await import("./NovoLote");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(NovoLote))),
    fireEvent: rtl.fireEvent,
  };
}

const CONFIG_URGENTE = {
  configuracoes: { tipos_edicao_ativos: ["cor_luz"], modelo_editor_imagem: "m", velocidade_padrao: "urgente" },
  showSkeleton: false,
  error: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseConfiguracoes.mockReturnValue(CONFIG_URGENTE);
});

describe("NovoLote — loading", () => {
  it("shows the form skeleton while capacidades is pending", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: true, error: null, refetch: vi.fn() });
    const { getByTestId } = await renderPage();
    expect(getByTestId("novo-lote-loading")).toBeTruthy();
  });
});

describe("NovoLote — error", () => {
  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: false, error: new Error("x"), refetch });
    const { getByText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe("NovoLote — permission denied", () => {
  it("shows the sem-permissão state when pode_criar_lote is false", async () => {
    mockUseCapacidades.mockReturnValue({
      capacidades: { ...CAPACIDADES_OK, pode_criar_lote: false },
      showSkeleton: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("novo-lote-sem-permissao")).toBeTruthy();
  });
});

describe("NovoLote — modelo ausente", () => {
  it("blocks the form and explains why when no model is configured", async () => {
    mockUseCapacidades.mockReturnValue({
      capacidades: { ...CAPACIDADES_OK, modelo_configurado: false },
      showSkeleton: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByTestId, queryByLabelText } = await renderPage();
    expect(getByTestId("novo-lote-modelo-ausente")).toBeTruthy();
    expect(queryByLabelText("Nome do lote")).toBeNull();
  });
});

describe("NovoLote — success (form)", () => {
  beforeEach(() => {
    mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES_OK, showSkeleton: false, error: null, refetch: vi.fn() });
  });

  it("renders the form with Econômico locked and its server-supplied reason", async () => {
    const { getByText } = await renderPage();
    expect(getByText("Econômico (bloqueado)")).toBeTruthy();
    expect(getByText("Motivo: modelo_sem_batch")).toBeTruthy();
  });

  it("keeps Criar lote disabled until nome + a valid Vista codigo are filled", async () => {
    const { getByText, getByLabelText, fireEvent } = await renderPage();
    const criarBtn = getByText("Criar lote").closest("button") as HTMLButtonElement;
    expect(criarBtn.disabled).toBe(true);

    fireEvent.click(getByText("Vista (código do imóvel)"));
    fireEvent.change(getByLabelText("Nome do lote"), { target: { value: "Apto 1" } });
    fireEvent.change(getByLabelText("Código do imóvel no Vista"), { target: { value: "123" } });

    expect(criarBtn.disabled).toBe(false);
  });

  it("on submit via Vista: creates the lote, pulls Vista with the NEW id, then submits — in order", async () => {
    mockCriarLote.mockResolvedValue({ id: "novo-lote-1", nome: "Apto 1" });
    mockLoteVista.mockResolvedValue({});
    mockSubmeterLote.mockResolvedValue({});

    const { getByText, getByLabelText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Vista (código do imóvel)"));
    fireEvent.change(getByLabelText("Nome do lote"), { target: { value: "Apto 1" } });
    fireEvent.change(getByLabelText("Código do imóvel no Vista"), { target: { value: "999" } });

    fireEvent.click(getByText("Criar lote"));

    await vi.waitFor(() => expect(mockSubmeterLote).toHaveBeenCalled());

    expect(mockCriarLote).toHaveBeenCalledWith({ nome: "Apto 1", imovel: null, velocidade: "urgente" });
    expect(mockLoteVista).toHaveBeenCalledWith({ loteId: "novo-lote-1", body: { codigo: "999" } });
    expect(mockSubmeterLote).toHaveBeenCalledWith("novo-lote-1");
    expect(mockUploadFotos).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith("/edicao-fotos");

    // order: criar -> vista -> submeter
    const criarOrder = mockCriarLote.mock.invocationCallOrder[0];
    const vistaOrder = mockLoteVista.mock.invocationCallOrder[0];
    const submeterOrder = mockSubmeterLote.mock.invocationCallOrder[0];
    expect(criarOrder).toBeLessThan(vistaOrder);
    expect(vistaOrder).toBeLessThan(submeterOrder);
  });
});

describe("NovoLote — velocidade (W4)", () => {
  const CAPACIDADES_ECO = { ...CAPACIDADES_OK, economico_disponivel: true, economico_bloqueado_motivo: null };

  async function fillVista(page: Awaited<ReturnType<typeof renderPage>>) {
    page.fireEvent.click(page.getByText("Vista (código do imóvel)"));
    page.fireEvent.change(page.getByLabelText("Nome do lote"), { target: { value: "Apto 2" } });
    page.fireEvent.change(page.getByLabelText("Código do imóvel no Vista"), { target: { value: "42" } });
  }

  it("unlocks Econômico when capacidades allows it and sends the choice", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES_ECO, showSkeleton: false, error: null, refetch: vi.fn() });
    mockCriarLote.mockResolvedValue({ id: "l-eco", nome: "Apto 2" });
    mockLoteVista.mockResolvedValue({});
    mockSubmeterLote.mockResolvedValue({});
    const page = await renderPage();
    expect(page.queryByText("Econômico (bloqueado)")).toBeNull();
    const eco = page.getByText("Econômico").closest("button") as HTMLButtonElement;
    expect(eco.disabled).toBe(false);
    page.fireEvent.click(eco);
    await fillVista(page);
    expect(eco.getAttribute("aria-pressed")).toBe("true");
    page.fireEvent.click(page.getByText("Criar lote"));
    await vi.waitFor(() => expect(mockSubmeterLote).toHaveBeenCalledWith("l-eco"));
    expect(mockCriarLote).toHaveBeenCalledWith({ nome: "Apto 2", imovel: null, velocidade: "economico" });
  });

  it("preselects the org's Econômico default when available", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES_ECO, showSkeleton: false, error: null, refetch: vi.fn() });
    mockUseConfiguracoes.mockReturnValue({
      ...CONFIG_URGENTE,
      configuracoes: { ...CONFIG_URGENTE.configuracoes, velocidade_padrao: "economico" },
    });
    const page = await renderPage();
    const eco = page.getByText("Econômico").closest("button") as HTMLButtonElement;
    expect(eco.getAttribute("aria-pressed")).toBe("true");
    expect(page.getByText(/50% de desconto/)).toBeTruthy();
  });

  it("says so when the org default is Econômico but it is unavailable", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES_OK, showSkeleton: false, error: null, refetch: vi.fn() });
    mockUseConfiguracoes.mockReturnValue({
      ...CONFIG_URGENTE,
      configuracoes: { ...CONFIG_URGENTE.configuracoes, velocidade_padrao: "economico" },
    });
    const page = await renderPage();
    expect(page.getByText("Econômico (bloqueado)")).toBeTruthy();
    expect(page.getByRole("status").textContent).toContain("usará Urgente");
    const urgente = page.getByText("Urgente").closest("button") as HTMLButtonElement;
    expect(urgente.getAttribute("aria-pressed")).toBe("true");
  });

  it("shows a skeleton for the speed row while the org settings load", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES_OK, showSkeleton: false, error: null, refetch: vi.fn() });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: undefined, showSkeleton: true, error: null });
    const page = await renderPage();
    expect(page.getByTestId("novo-lote-velocidade-loading")).toBeTruthy();
    expect(page.queryByText("Urgente")).toBeNull();
  });

  it("requires an explicit choice when the org settings fail to load", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES_OK, showSkeleton: false, error: null, refetch: vi.fn() });
    mockUseConfiguracoes.mockReturnValue({ configuracoes: undefined, showSkeleton: false, error: new Error("x") });
    const page = await renderPage();
    await fillVista(page);
    const criarBtn = page.getByText("Criar lote").closest("button") as HTMLButtonElement;
    expect(criarBtn.disabled).toBe(true);
    expect(page.getByRole("alert").textContent).toContain("escolha a velocidade");
    page.fireEvent.click(page.getByText("Urgente"));
    expect(criarBtn.disabled).toBe(false);
  });
});
