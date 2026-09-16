/**
 * Referencias.test.tsx — the capability lock (pool = platform admin ∨
 * curator), loading/error/empty/refreshing states, the full-pool block, the
 * multipart upload payload, archive through the seed card, and the
 * platform-admin-only limit editor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseReferencias = vi.fn();
const mockUseConfigPlataforma = vi.fn();
const mockCriar = vi.fn();
const mockArquivar = vi.fn();
const mockAtualizarPlataforma = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useReferencias: (...a: any[]) => mockUseReferencias(...a),
    useConfiguracoesPlataforma: (...a: any[]) => mockUseConfigPlataforma(...a),
    useCriarReferencia: () => ({ mutateAsync: mockCriar, isPending: false }),
    useArquivarReferencia: () => ({ mutateAsync: mockArquivar, isPending: false, variables: undefined }),
    useAtualizarConfiguracoesPlataforma: () => ({ mutateAsync: mockAtualizarPlataforma, isPending: false }),
  };
});

const OPCOES = { comodos: ["sala", "area_externa"], tipos_edicao: ["cor_luz", "ceu"] };
const PAR = {
  id: "ref-1",
  antes_url: "https://x/antes.jpg",
  depois_url: "https://x/depois.jpg",
  comodo: "area_externa",
  tipos_edicao: ["ceu"],
  nota: "Céu limpo",
  arquivada_em: null,
};

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

function referencias(overrides: Partial<any> = {}) {
  return {
    referencias: [PAR],
    total: 1,
    pool: { pares_ativos: 1, limite_pares: null, cheio: false },
    opcoes: OPCOES,
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Referencias } = await import("./Referencias");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Referencias))),
    rtl,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCapacidades.mockReturnValue({ capacidades: capacidades(), showSkeleton: false });
  mockUseReferencias.mockReturnValue(referencias());
  mockUseConfigPlataforma.mockReturnValue({
    configuracoes: {
      velocidade_default: "urgente",
      notificacoes_globais_ativas: true,
      preco_storage_gb_mes_usd: null,
      limite_pares_referencia: 10,
    },
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
  });
});

describe("Referencias — access", () => {
  it("locks the page for a caller without pode_gerir_pool, never querying the pool", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ pode_gerir_pool: false }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("referencias-restrito")).toBeTruthy();
    expect(mockUseReferencias).not.toHaveBeenCalled();
  });

  it("shows a skeleton (not the lock) while capabilities load", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: true });
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("referencias-carregando")).toBeTruthy();
    expect(queryByTestId("referencias-restrito")).toBeNull();
  });
});

describe("Referencias — list states", () => {
  it("renders the grid skeleton while the pool is pending", async () => {
    mockUseReferencias.mockReturnValue(referencias({ referencias: [], pool: undefined, opcoes: undefined, showSkeleton: true }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("referencias-loading")).toBeTruthy();
  });

  it("keeps the grid mounted while refreshing (never a skeleton over data)", async () => {
    mockUseReferencias.mockReturnValue(referencias({ isRefreshing: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("referencias-grid")).toBeTruthy();
    expect(getByTestId("referencias-atualizando")).toBeTruthy();
    expect(queryByTestId("referencias-loading")).toBeNull();
  });

  it("shows the empty state", async () => {
    mockUseReferencias.mockReturnValue(referencias({ referencias: [], total: 0, pool: { pares_ativos: 0, limite_pares: null, cheio: false } }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("referencias-vazio")).toBeTruthy();
  });

  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseReferencias.mockReturnValue(referencias({ referencias: [], error: new Error("boom"), refetch }));
    const { getByText, rtl } = await renderPage();
    rtl.fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("renders the seed card with pt-BR labels for the backend literals", async () => {
    const { getByTestId, rtl } = await renderPage();
    const grid = rtl.within(getByTestId("referencias-grid"));
    expect(grid.getByText("Área externa")).toBeTruthy();
    expect(grid.getByText("Substituição de céu")).toBeTruthy();
    expect(grid.getByText("Céu limpo")).toBeTruthy();
    expect(grid.queryByText("area_externa")).toBeNull();
  });
});

describe("Referencias — pool limit", () => {
  it("reports occupancy and disables the upload when the pool is full", async () => {
    mockUseReferencias.mockReturnValue(referencias({ pool: { pares_ativos: 3, limite_pares: 3, cheio: true } }));
    const { getByTestId, getByRole } = await renderPage();
    expect(getByTestId("pool-ocupacao").textContent).toContain("3 de 3 pares ativos");
    expect(getByTestId("pool-ocupacao").textContent).toContain("pool cheio");
    expect((getByRole("button", { name: /Enviar par/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the limit editor only to a platform admin", async () => {
    const curador = await renderPage();
    expect(curador.queryByLabelText("Limite do pool (em pares)")).toBeNull();
    expect(mockUseConfigPlataforma).not.toHaveBeenCalled();
    curador.unmount();

    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "platform" }), showSkeleton: false });
    const admin = await renderPage();
    const input = admin.getByLabelText("Limite do pool (em pares)") as HTMLInputElement;
    expect(input.value).toBe("10");
    admin.rtl.fireEvent.change(input, { target: { value: "" } });
    admin.rtl.fireEvent.click(admin.getByRole("button", { name: "Salvar limite" }));
    await admin.rtl.waitFor(() => expect(mockAtualizarPlataforma).toHaveBeenCalled());
    // Sends the WHOLE settings object; blank = 0 = unlimited.
    expect(mockAtualizarPlataforma).toHaveBeenCalledWith({
      velocidade_default: "urgente",
      notificacoes_globais_ativas: true,
      preco_storage_gb_mes_usd: null,
      limite_pares_referencia: 0,
    });
  });
});

describe("Referencias — upload + archive", () => {
  it("sends both files, the room, the edit types and the note", async () => {
    mockCriar.mockResolvedValue(PAR);
    const { getByLabelText, getByRole, rtl } = await renderPage();
    const antes = new File(["a"], "antes.jpg", { type: "image/jpeg" });
    const depois = new File(["d"], "depois.jpg", { type: "image/jpeg" });
    rtl.fireEvent.change(getByLabelText("Antes"), { target: { files: [antes] } });
    rtl.fireEvent.change(getByLabelText("Depois"), { target: { files: [depois] } });
    rtl.fireEvent.click(getByLabelText("Cor e luz"));
    rtl.fireEvent.change(getByLabelText("Nota"), { target: { value: "  Luz quente  " } });
    const enviar = getByRole("button", { name: /Enviar par/ }) as HTMLButtonElement;
    expect(enviar.disabled).toBe(true); // no room chosen yet — there is no default
    rtl.fireEvent.change(getByLabelText("Cômodo"), { target: { value: "sala" } });
    expect(enviar.disabled).toBe(false);
    rtl.fireEvent.click(enviar);
    await rtl.waitFor(() => expect(mockCriar).toHaveBeenCalled());
    expect(mockCriar).toHaveBeenCalledWith({
      antes,
      depois,
      comodo: "sala",
      tipos_edicao: ["cor_luz"],
      nota: "Luz quente",
    });
  });

  it("surfaces pool_cheio from a race as a toast, not a crash", async () => {
    const { ApiError } = await import("@noctusai/lib/api");
    const { toast } = await import("sonner");
    mockCriar.mockRejectedValue(new ApiError(409, "cheio", { detail: "x", code: "pool_cheio" }));
    const { getByLabelText, getByRole, rtl } = await renderPage();
    rtl.fireEvent.change(getByLabelText("Antes"), { target: { files: [new File(["a"], "a.jpg")] } });
    rtl.fireEvent.change(getByLabelText("Depois"), { target: { files: [new File(["d"], "d.jpg")] } });
    rtl.fireEvent.change(getByLabelText("Cômodo"), { target: { value: "sala" } });
    rtl.fireEvent.click(getByRole("button", { name: /Enviar par/ }));
    await rtl.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível enviar o par.", {
        description: "O pool está cheio — arquive um par ou aumente o limite.",
      }),
    );
  });

  it("archives through the seed card's two-step confirm", async () => {
    mockArquivar.mockResolvedValue({ ...PAR, arquivada_em: "2026-09-16T00:00:00Z" });
    const { getByRole, rtl } = await renderPage();
    rtl.fireEvent.click(getByRole("button", { name: "Arquivar" }));
    rtl.fireEvent.click(getByRole("button", { name: "Confirmar" }));
    await rtl.waitFor(() => expect(mockArquivar).toHaveBeenCalledWith("ref-1"));
  });

  it("asks the hook for page 1 without archived pairs by default, and toggles them", async () => {
    const { getByLabelText, rtl } = await renderPage();
    expect(mockUseReferencias).toHaveBeenLastCalledWith({ page: 1, pageSize: 24, incluirArquivadas: false });
    rtl.fireEvent.click(getByLabelText("Mostrar arquivadas"));
    expect(mockUseReferencias).toHaveBeenLastCalledWith({ page: 1, pageSize: 24, incluirArquivadas: true });
  });
});
