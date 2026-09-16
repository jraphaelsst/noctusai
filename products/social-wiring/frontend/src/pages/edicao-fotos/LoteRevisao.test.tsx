/**
 * LoteRevisao.test.tsx — canonical-organ consumption (`PhotoReviewGrid`
 * receives the right props, not a re-implemented grid), the zip-readiness
 * predicate ("409 until every photo is decided… `falhou` excluded and never
 * blocks the batch" — contract §3), and the error state. `PhotoReviewGrid`
 * itself is stubbed (its own states are covered by the seed's
 * `PhotoReviewGrid.test.tsx`) — this file only asserts THIS page wires it
 * correctly, same strategy as `PortalRoi.test.tsx` stubbing
 * `CampanhaManagerDialog`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseCapacidades = vi.fn();
const mockUseLote = vi.fn();
const mockUseRevisao = vi.fn();
const mockDecidirFoto = vi.fn();
const mockRetentarFoto = vi.fn();
const mockBaixarZip = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useEdicaoFotos")>("@/hooks/useEdicaoFotos");
  return {
    ...actual,
    useCapacidades: (...a: any[]) => mockUseCapacidades(...a),
    useLote: (...a: any[]) => mockUseLote(...a),
    useRevisao: (...a: any[]) => mockUseRevisao(...a),
    useDecidirFoto: () => ({ mutateAsync: mockDecidirFoto }),
    useRetentarFoto: () => ({ mutateAsync: mockRetentarFoto }),
    useBaixarZip: () => ({ mutateAsync: mockBaixarZip, isPending: false }),
  };
});

let lastGridProps: any = null;
vi.mock("@noctusai/lib/photo-editing/PhotoReviewGrid", () => ({
  PhotoReviewGrid: (props: any) => {
    lastGridProps = props;
    return <div data-testid="photo-review-grid-stub">{props.fotos.length}</div>;
  },
}));

function foto(overrides: Partial<any> = {}) {
  return {
    id: "f1",
    url_antes: "a.jpg",
    url_depois: "a-edit.jpg",
    estado: "aguardando_decisao",
    decisao: null,
    comentario: null,
    ...overrides,
  };
}

const CAPACIDADES = {
  pode_criar_lote: true,
  pode_ver_veredito: true,
  pode_gerir_pool: false,
  pode_aprovar_regras: false,
  pode_ativar_guia: false,
  dashboard: "org",
  modelo_configurado: true,
  economico_disponivel: false,
  economico_bloqueado_motivo: null,
  tipos_edicao_ativos: ["cor_luz"],
  limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
};

async function renderPage(loteId = "lote-1") {
  const React = (await import("react")).default;
  const { default: LoteRevisao } = await import("./LoteRevisao");
  const { MemoryRouter, Routes, Route } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: [`/edicao-fotos/lotes/${loteId}/revisao`] },
        React.createElement(
          Routes,
          null,
          React.createElement(Route, {
            path: "/edicao-fotos/lotes/:loteId/revisao",
            element: React.createElement(LoteRevisao),
          }),
        ),
      ),
    ),
    fireEvent: rtl.fireEvent,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  lastGridProps = null;
  mockUseCapacidades.mockReturnValue({ capacidades: CAPACIDADES });
  mockUseLote.mockReturnValue({ lote: { id: "lote-1", nome: "Apto 302" }, showSkeleton: false });
});

describe("LoteRevisao — canonical organ consumption", () => {
  it("passes podeVerVeredito from capacidades, and the loading-state contract fields straight through from useRevisao", async () => {
    mockUseRevisao.mockReturnValue({
      fotos: [foto()],
      showSkeleton: false,
      isRefreshing: true,
      error: null,
      refetch: vi.fn(),
    });

    await renderPage();

    expect(lastGridProps.podeVerVeredito).toBe(true);
    expect(lastGridProps.showSkeleton).toBe(false);
    expect(lastGridProps.isRefreshing).toBe(true);
    expect(typeof lastGridProps.onDecidir).toBe("function");
    expect(typeof lastGridProps.onRetry).toBe("function");
  });
});

describe("LoteRevisao — error", () => {
  it("shows the error state (and never renders the grid) when useRevisao errors", async () => {
    mockUseRevisao.mockReturnValue({
      fotos: [],
      showSkeleton: false,
      isRefreshing: false,
      error: new Error("boom"),
      refetch: vi.fn(),
    });
    const { getByText, queryByTestId } = await renderPage();
    expect(getByText("Não foi possível carregar a revisão deste lote.")).toBeTruthy();
    expect(queryByTestId("photo-review-grid-stub")).toBeNull();
  });
});

describe("LoteRevisao — zip readiness", () => {
  it("keeps the zip button disabled while any decidível photo is undecided", async () => {
    mockUseRevisao.mockReturnValue({
      fotos: [foto({ id: "f1", decisao: "aprovar" }), foto({ id: "f2", decisao: null })],
      showSkeleton: false,
      isRefreshing: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByText } = await renderPage();
    const zipBtn = getByText("Baixar zip").closest("button") as HTMLButtonElement;
    expect(zipBtn.disabled).toBe(true);
  });

  it("ignores falhou photos for readiness (they never block the batch — contract §3)", async () => {
    mockUseRevisao.mockReturnValue({
      fotos: [foto({ id: "f1", decisao: "aprovar" }), foto({ id: "f2", estado: "falhou", decisao: null })],
      showSkeleton: false,
      isRefreshing: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByText, fireEvent } = await renderPage("lote-1");
    const zipBtn = getByText("Baixar zip").closest("button") as HTMLButtonElement;
    expect(zipBtn.disabled).toBe(false);

    mockBaixarZip.mockResolvedValue(undefined);
    fireEvent.click(zipBtn);
    await vi.waitFor(() => expect(mockBaixarZip).toHaveBeenCalled());
    expect(mockBaixarZip).toHaveBeenCalledWith({ loteId: "lote-1", nomeArquivo: "Apto-302.zip" });
  });

  it("disables the zip button when there are zero decidível photos (nothing to zip yet)", async () => {
    mockUseRevisao.mockReturnValue({
      fotos: [foto({ estado: "falhou", decisao: null })],
      showSkeleton: false,
      isRefreshing: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByText } = await renderPage();
    const zipBtn = getByText("Baixar zip").closest("button") as HTMLButtonElement;
    expect(zipBtn.disabled).toBe(true);
  });
});
