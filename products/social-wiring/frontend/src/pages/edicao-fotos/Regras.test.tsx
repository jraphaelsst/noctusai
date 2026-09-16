/**
 * Regras.test.tsx (W7) — the capability lock, loading/error/empty/refreshing
 * states, the propor-agora / manual-create / approve / reject / edit /
 * archive actions, the platform-admin-only override + config panel gating,
 * and the effective-guide view (including the "no active guide yet" state).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseRegras = vi.fn();
const mockUseGuiaEfetivo = vi.fn();
const mockUseConfiguracoesPlataforma = vi.fn();
const mockCriar = vi.fn();
const mockEditar = vi.fn();
const mockAprovar = vi.fn();
const mockRejeitar = vi.fn();
const mockProporAgora = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useRegras: (...a: any[]) => mockUseRegras(...a),
    useGuiaEfetivo: (...a: any[]) => mockUseGuiaEfetivo(...a),
    useConfiguracoesPlataforma: (...a: any[]) => mockUseConfiguracoesPlataforma(...a),
    useCriarRegra: () => ({ mutateAsync: mockCriar, isPending: false }),
    useEditarRegra: () => ({ mutateAsync: mockEditar, isPending: false }),
    useAprovarRegra: () => ({ mutateAsync: mockAprovar, isPending: false }),
    useRejeitarRegra: () => ({ mutateAsync: mockRejeitar, isPending: false }),
    useProporRegrasAgora: () => ({ mutateAsync: mockProporAgora, isPending: false }),
  };
});

function regra(overrides: Partial<any> = {}) {
  return {
    id: "r1",
    texto: "Não escurecer o céu",
    status: "proposta",
    origem_comentarios: [],
    decidido_por: null,
    decidido_em: null,
    override_platform_admin: false,
    criado_em: "2026-09-16T18:00:00Z",
    ...overrides,
  };
}

function regrasState(overrides: Partial<any> = {}) {
  return {
    regras: [regra()],
    total: 1,
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

function guiaEfetivoState(overrides: Partial<any> = {}) {
  return {
    atual: null,
    historico: [],
    total: 0,
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

function capacidades(overrides: Partial<any> = {}) {
  return {
    pode_criar_lote: false,
    pode_ver_veredito: false,
    pode_gerir_pool: false,
    pode_aprovar_regras: true,
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

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Regras } = await import("./Regras");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Regras))),
    rtl,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCapacidades.mockReturnValue({ capacidades: capacidades(), showSkeleton: false });
  mockUseRegras.mockReturnValue(regrasState());
  mockUseGuiaEfetivo.mockReturnValue(guiaEfetivoState());
  mockUseConfiguracoesPlataforma.mockReturnValue({
    configuracoes: { rule_proposal_debounce_seconds: 1800, max_rejections_per_proposal: 50 },
    showSkeleton: false,
  });
});

describe("Regras — access + states", () => {
  it("locks the page without pode_aprovar_regras and never lists rules", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ pode_aprovar_regras: false }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("regras-restrito")).toBeTruthy();
    expect(mockUseRegras).not.toHaveBeenCalled();
  });

  it("shows the skeleton while capacidades are pending", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("regras-loading")).toBeTruthy();
  });

  it("keeps the list mounted while refreshing", async () => {
    mockUseRegras.mockReturnValue(regrasState({ isRefreshing: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("regras-lista")).toBeTruthy();
    expect(getByTestId("regras-atualizando")).toBeTruthy();
    expect(queryByTestId("regras-loading")).toBeNull();
  });

  it("shows the empty state when there are no rules", async () => {
    mockUseRegras.mockReturnValue(regrasState({ regras: [], total: 0 }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("regras-vazio")).toBeTruthy();
  });

  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseRegras.mockReturnValue(regrasState({ regras: [], error: new Error("x"), refetch }));
    const { getByText, rtl } = await renderPage();
    rtl.fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });
});

describe("Regras — lifecycle actions", () => {
  it("approves and rejects a proposed rule", async () => {
    mockAprovar.mockResolvedValue(regra({ status: "aprovada" }));
    const { getByTestId, rtl } = await renderPage();
    const card = rtl.within(getByTestId("regra-r1"));
    rtl.fireEvent.click(card.getByRole("button", { name: /Aprovar/ }));
    await rtl.waitFor(() => expect(mockAprovar).toHaveBeenCalledWith("r1"));
    rtl.fireEvent.click(card.getByRole("button", { name: /Rejeitar/ }));
    await rtl.waitFor(() => expect(mockRejeitar).toHaveBeenCalledWith("r1"));
  });

  it("edits an approved rule's text", async () => {
    mockUseRegras.mockReturnValue(regrasState({ regras: [regra({ status: "aprovada" })] }));
    mockEditar.mockResolvedValue(regra({ status: "aprovada", texto: "Novo texto" }));
    const { getByTestId, rtl } = await renderPage();
    const card = rtl.within(getByTestId("regra-r1"));
    rtl.fireEvent.click(card.getByRole("button", { name: /Editar/ }));
    const textarea = getByTestId("regra-r1-editar-form").querySelector("textarea") as HTMLTextAreaElement;
    rtl.fireEvent.change(textarea, { target: { value: "Novo texto" } });
    rtl.fireEvent.click(card.getByRole("button", { name: "Salvar" }));
    await rtl.waitFor(() => expect(mockEditar).toHaveBeenCalledWith({ regraId: "r1", texto: "Novo texto" }));
  });

  it("agency admin (dashboard=org) cannot archive an approved rule", async () => {
    mockUseRegras.mockReturnValue(regrasState({ regras: [regra({ status: "aprovada" })] }));
    const { getByTestId, rtl } = await renderPage();
    expect(rtl.within(getByTestId("regra-r1")).queryByRole("button", { name: "Arquivar" })).toBeNull();
  });

  it("platform admin (dashboard=platform) can archive an approved rule", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "platform" }), showSkeleton: false });
    mockUseRegras.mockReturnValue(regrasState({ regras: [regra({ status: "aprovada" })] }));
    const { getByTestId, rtl } = await renderPage();
    const archivar = rtl.within(getByTestId("regra-r1")).getByRole("button", { name: "Arquivar" });
    rtl.fireEvent.click(archivar);
    await rtl.waitFor(() => expect(mockRejeitar).toHaveBeenCalledWith("r1"));
  });

  it("creates a manual rule (auto-approved)", async () => {
    mockCriar.mockResolvedValue(regra({ status: "aprovada" }));
    const { getByRole, getByLabelText, rtl } = await renderPage();
    rtl.fireEvent.click(getByRole("button", { name: /Escrever regra manualmente/ }));
    const salvar = getByRole("button", { name: "Salvar regra" }) as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    rtl.fireEvent.change(getByLabelText(/Texto da regra/), { target: { value: "Não usar céu roxo" } });
    rtl.fireEvent.click(salvar);
    await rtl.waitFor(() => expect(mockCriar).toHaveBeenCalledWith({ texto: "Não usar céu roxo" }));
  });

  it("explains regra_duplicada when a manual create collides", async () => {
    const { ApiError } = await import("@noctusai/lib/api");
    const { toast } = await import("sonner");
    mockCriar.mockRejectedValue(new ApiError(409, "dup", { detail: "x", code: "regra_duplicada" }));
    const { getByRole, getByLabelText, rtl } = await renderPage();
    rtl.fireEvent.click(getByRole("button", { name: /Escrever regra manualmente/ }));
    rtl.fireEvent.change(getByLabelText(/Texto da regra/), { target: { value: "Não X" } });
    rtl.fireEvent.click(getByRole("button", { name: "Salvar regra" }));
    await rtl.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível criar a regra.", {
        description: "Já existe uma regra equivalente para esta organização.",
      }),
    );
  });

  it("runs the AI proposer now via propor-agora", async () => {
    mockProporAgora.mockResolvedValue({ job_id: "j1", status: "pending" });
    const { getByRole, rtl } = await renderPage();
    rtl.fireEvent.click(getByRole("button", { name: /Propor agora/ }));
    await rtl.waitFor(() => expect(mockProporAgora).toHaveBeenCalled());
  });
});

describe("Regras — effective guide view", () => {
  it("shows the no-active-guide notice when atual is null", async () => {
    const { getByText } = await renderPage();
    expect(getByText(/Nenhum guia de estilo ativo ainda/)).toBeTruthy();
  });

  it("shows the composed guide text when atual is present", async () => {
    mockUseGuiaEfetivo.mockReturnValue(
      guiaEfetivoState({
        atual: { id: "eg1", guia_estilo_id: "g1", conjunto_regras_id: null, texto: "guia composto", sha256: "abc" },
        historico: [{ id: "eg1", guia_estilo_id: "g1", conjunto_regras_id: null, texto: "guia composto", sha256: "abc", criado_em: "2026-09-16T18:00:00Z" }],
        total: 1,
      }),
    );
    const { getByTestId } = await renderPage();
    expect(getByTestId("guia-efetivo-texto").textContent).toContain("guia composto");
  });
});

describe("Regras — platform-only config panel", () => {
  it("hides the rule-proposer config panel for an agency admin", async () => {
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("regras-config-proponente")).toBeNull();
  });

  it("shows the read-only debounce/threshold values for a platform admin", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "platform" }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("regras-config-proponente").textContent).toContain("1800");
    expect(getByTestId("regras-config-proponente").textContent).toContain("50");
  });
});
