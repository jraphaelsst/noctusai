/**
 * GuiasEstilo.test.tsx — the capability lock, loading/error/empty/refreshing
 * states, the "no active guide" warning, the manual-draft path (the R1
 * no-AI unblock), activation only on drafts, restore on superseded versions,
 * and the regenerate button's pool_vazio handling.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseGuias = vi.fn();
const mockCriar = vi.fn();
const mockAtivar = vi.fn();
const mockRestaurar = vi.fn();
const mockRegenerar = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useGuias: (...a: any[]) => mockUseGuias(...a),
    useCriarGuia: () => ({ mutateAsync: mockCriar, isPending: false }),
    useAtivarGuia: () => ({ mutateAsync: mockAtivar, isPending: false }),
    useRestaurarGuia: () => ({ mutateAsync: mockRestaurar, isPending: false }),
    useRegenerarGuia: () => ({ mutateAsync: mockRegenerar, isPending: false }),
  };
});

function guia(overrides: Partial<any> = {}) {
  return {
    id: `g-${overrides.versao ?? 1}`,
    versao: 1,
    status: "rascunho",
    texto: "- Luz natural\n",
    sha256: "s",
    gerado_de_versao: null,
    origem: "manual",
    criado_por: "u",
    criado_em: "2026-09-16T18:00:00Z",
    ativado_por: null,
    ativado_em: null,
    ...overrides,
  };
}

function guias(overrides: Partial<any> = {}) {
  return {
    guias: [
      guia({ versao: 3, status: "rascunho", origem: "ia", criado_por: null, gerado_de_versao: 2 }),
      guia({ versao: 2, status: "ativa", ativado_em: "2026-09-16T19:00:00Z" }),
      guia({ versao: 1, status: "substituida" }),
    ],
    total: 3,
    versaoAtiva: 2,
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
    pode_gerir_pool: true,
    pode_aprovar_regras: false,
    pode_ativar_guia: true,
    dashboard: null,
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
  const { default: GuiasEstilo } = await import("./GuiasEstilo");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(GuiasEstilo))),
    rtl,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCapacidades.mockReturnValue({ capacidades: capacidades(), showSkeleton: false });
  mockUseGuias.mockReturnValue(guias());
});

describe("GuiasEstilo — access + states", () => {
  it("locks the page without pode_ativar_guia and never lists versions", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ pode_ativar_guia: false }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("guias-restrito")).toBeTruthy();
    expect(mockUseGuias).not.toHaveBeenCalled();
  });

  it("shows the skeleton while versions are pending, without the no-active warning", async () => {
    mockUseGuias.mockReturnValue(guias({ guias: [], total: 0, versaoAtiva: null, showSkeleton: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("guias-loading")).toBeTruthy();
    expect(queryByTestId("sem-guia-ativo")).toBeNull();
  });

  it("keeps the list mounted while refreshing", async () => {
    mockUseGuias.mockReturnValue(guias({ isRefreshing: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("guias-lista")).toBeTruthy();
    expect(getByTestId("guias-atualizando")).toBeTruthy();
    expect(queryByTestId("guias-loading")).toBeNull();
  });

  it("warns that batches are blocked when no version is active, and shows the empty state", async () => {
    mockUseGuias.mockReturnValue(guias({ guias: [], total: 0, versaoAtiva: null }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("sem-guia-ativo")).toBeTruthy();
    expect(getByTestId("guias-vazio")).toBeTruthy();
  });

  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseGuias.mockReturnValue(guias({ guias: [], error: new Error("x"), refetch }));
    const { getByText, rtl } = await renderPage();
    rtl.fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });
});

describe("GuiasEstilo — lifecycle actions", () => {
  it("offers Ativar only on drafts and Restaurar only on superseded versions", async () => {
    const { getByTestId } = await renderPage();
    const rtl = await import("@testing-library/react");
    const v3 = rtl.within(getByTestId("guia-v3"));
    const v2 = rtl.within(getByTestId("guia-v2"));
    const v1 = rtl.within(getByTestId("guia-v1"));
    expect(v3.queryByRole("button", { name: "Ativar" })).toBeTruthy();
    expect(v3.getByText("Gerada por IA")).toBeTruthy();
    expect(v2.queryByRole("button", { name: "Ativar" })).toBeNull();
    expect(v2.queryByRole("button", { name: /Restaurar/ })).toBeNull();
    expect(v1.queryByRole("button", { name: "Ativar" })).toBeNull();
    expect(v1.queryByRole("button", { name: /Restaurar/ })).toBeTruthy();
  });

  it("activates a draft and restores a superseded version by number", async () => {
    mockAtivar.mockResolvedValue(guia({ versao: 3, status: "ativa" }));
    mockRestaurar.mockResolvedValue(guia({ versao: 4 }));
    const { getByTestId, rtl } = await renderPage();
    rtl.fireEvent.click(rtl.within(getByTestId("guia-v3")).getByRole("button", { name: "Ativar" }));
    await rtl.waitFor(() => expect(mockAtivar).toHaveBeenCalledWith(3));
    rtl.fireEvent.click(rtl.within(getByTestId("guia-v1")).getByRole("button", { name: /Restaurar/ }));
    await rtl.waitFor(() => expect(mockRestaurar).toHaveBeenCalledWith(1));
  });

  it("creates a manual draft from the written text", async () => {
    mockCriar.mockResolvedValue(guia({ versao: 4 }));
    const { getByRole, getByLabelText, rtl } = await renderPage();
    rtl.fireEvent.click(getByRole("button", { name: /Escrever guia/ }));
    const salvar = getByRole("button", { name: "Salvar rascunho" }) as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    rtl.fireEvent.change(getByLabelText("Texto do guia"), { target: { value: "- Céu azul" } });
    rtl.fireEvent.click(salvar);
    await rtl.waitFor(() => expect(mockCriar).toHaveBeenCalledWith({ texto: "- Céu azul" }));
  });

  it("explains pool_vazio when regeneration is refused", async () => {
    const { ApiError } = await import("@noctusai/lib/api");
    const { toast } = await import("sonner");
    mockRegenerar.mockRejectedValue(new ApiError(409, "vazio", { detail: "x", code: "pool_vazio" }));
    const { getByRole, rtl } = await renderPage();
    rtl.fireEvent.click(getByRole("button", { name: /Regenerar com IA/ }));
    await rtl.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível regenerar o guia.", {
        description: "O pool de referências está vazio — envie pares antes de regenerar.",
      }),
    );
  });
});
