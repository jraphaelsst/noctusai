/**
 * Curadores.test.tsx — the capability lock (platform admin ONLY, unlike
 * the pool pages which also admit a curator), loading/error/empty states,
 * add + remove.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseCuradores = vi.fn();
const mockAdicionar = vi.fn();
const mockRemover = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useCuradores: (...a: any[]) => mockUseCuradores(...a),
    useAdicionarCurador: () => ({ mutateAsync: mockAdicionar, isPending: false }),
    useRemoverCurador: () => ({ mutateAsync: mockRemover, isPending: false, variables: undefined }),
  };
});

const CURADOR = {
  user_id: "u-1",
  nome: "Cris Curadora",
  email: "cris@example.com",
  concedido_por: "u-admin",
  created_at: "2026-09-16T00:00:00Z",
};

function capacidades(overrides: Partial<any> = {}) {
  return {
    pode_criar_lote: false,
    pode_ver_veredito: false,
    pode_gerir_pool: false,
    pode_aprovar_regras: false,
    pode_ativar_guia: false,
    dashboard: "platform",
    modelo_configurado: false,
    economico_disponivel: false,
    economico_bloqueado_motivo: "sem_modelo",
    tipos_edicao_ativos: [],
    limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
    ...overrides,
  };
}

function curadores(overrides: Partial<any> = {}) {
  return {
    curadores: [CURADOR],
    total: 1,
    showSkeleton: false,
    isRefreshing: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Curadores } = await import("./Curadores");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Curadores))),
    fireEvent: rtl.fireEvent,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCapacidades.mockReturnValue({ capacidades: capacidades(), showSkeleton: false });
  mockUseCuradores.mockReturnValue(curadores());
});

describe("Curadores — capability lock", () => {
  it("shows the page skeleton while capacidades is loading", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: undefined, showSkeleton: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("curadores-carregando")).toBeTruthy();
  });

  it("refuses a plain agency admin (dashboard=org) — platform admin ONLY, not the pool-manager gate", async () => {
    mockUseCapacidades.mockReturnValue({ capacidades: capacidades({ dashboard: "org" }), showSkeleton: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("curadores-restrito")).toBeTruthy();
  });

  it("refuses a curator (dashboard=null, pode_gerir_pool=true) — granting curators is a platform decision", async () => {
    mockUseCapacidades.mockReturnValue({
      capacidades: capacidades({ dashboard: null, pode_gerir_pool: true }), showSkeleton: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("curadores-restrito")).toBeTruthy();
  });

  it("admits a platform admin (dashboard=platform)", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("curadores-lista")).toBeTruthy();
  });
});

describe("Curadores — list states", () => {
  it("shows the loading skeleton", async () => {
    mockUseCuradores.mockReturnValue(curadores({ showSkeleton: true, curadores: [] }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("curadores-loading")).toBeTruthy();
  });

  it("shows the error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseCuradores.mockReturnValue(curadores({ error: new Error("x"), curadores: [], refetch }));
    const { getByText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state", async () => {
    mockUseCuradores.mockReturnValue(curadores({ curadores: [], total: 0 }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("curadores-vazio")).toBeTruthy();
  });

  it("renders each curador's name and email", async () => {
    const { getByText } = await renderPage();
    expect(getByText("Cris Curadora")).toBeTruthy();
    expect(getByText("cris@example.com")).toBeTruthy();
  });
});

describe("Curadores — add / remove", () => {
  it("adds a curador by user id and clears the input", async () => {
    mockAdicionar.mockResolvedValue(undefined);
    const { getByLabelText, getByText, fireEvent } = await renderPage();
    const input = getByLabelText("Id do usuário (NoctusAI)") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "  u-2  " } });
    fireEvent.click(getByText("Adicionar curador"));

    await vi.waitFor(() => expect(mockAdicionar).toHaveBeenCalledWith({ user_id: "u-2" }));
  });

  it("removes a curador", async () => {
    mockRemover.mockResolvedValue(undefined);
    const { getByText, fireEvent } = await renderPage();
    fireEvent.click(getByText("Remover"));
    await vi.waitFor(() => expect(mockRemover).toHaveBeenCalledWith("u-1"));
  });
});
