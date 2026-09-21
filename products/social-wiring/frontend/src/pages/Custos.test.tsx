/**
 * Custos — four states (skeleton / error / empty / data), per
 * `CLAUDE/frontend.md`'s no-lying-loading-state rule
 * (`showSkeleton = isPending && !data`, never a bare `isLoading`).
 */
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseCustos = vi.fn();
vi.mock("@/hooks/useCustos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useCustos")>("@/hooks/useCustos");
  return { ...actual, useCustos: mockUseCustos };
});

const CUSTOS = {
  de: "2026-09-01",
  ate: "2026-09-21",
  total_brl: 42.5,
  fx_pendente: false,
  integracoes: [
    { nome: "llm", chamadas: 10, custo_brl: 30.5, fx_pendente: false, observacao: null },
    { nome: "infosimples", chamadas: 3, custo_brl: 12.0, fx_pendente: false, observacao: null },
    { nome: "d4sign", chamadas: 0, custo_brl: null, fx_pendente: false, observacao: "Custo por chamada não disponível — consulte seu plano D4Sign." },
    { nome: "google_maps", chamadas: 0, custo_brl: null, fx_pendente: false, observacao: "Custo por chamada não disponível — consulte seu plano Google Maps." },
  ],
  serie_diaria: [
    { data: "2026-09-20", custo_brl: 20.0 },
    { data: "2026-09-21", custo_brl: 22.5 },
  ],
  llm_por_modelo: [
    { provider: "anthropic", model: "claude-sonnet-5", chamadas: 10, total_tokens: 5000, custo_usd: 6.1, custo_brl: 30.5 },
  ],
};

async function render() {
  const React = (await import("react")).default;
  const { default: Custos } = await import("./Custos");
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(Custos));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Custos", () => {
  it("shows a skeleton while pending with no cached data (never a bare spinner over stale data)", async () => {
    mockUseCustos.mockReturnValue({ data: undefined, error: null, showSkeleton: true, isRefreshing: false });
    const { queryByTestId } = await render();
    expect(queryByTestId("custos-total")).toBeNull();
  });

  it("shows an error state distinct from empty when the request fails", async () => {
    mockUseCustos.mockReturnValue({ data: undefined, error: new Error("boom"), showSkeleton: false, isRefreshing: false });
    const { getByText, queryByTestId } = await render();
    expect(getByText(/não foi possível carregar/i)).toBeTruthy();
    expect(queryByTestId("custos-total")).toBeNull();
  });

  it("renders every integration card even when spend is zero, never omitting one", async () => {
    mockUseCustos.mockReturnValue({
      data: { ...CUSTOS, total_brl: 0, integracoes: CUSTOS.integracoes.map((i) => ({ ...i, custo_brl: 0, chamadas: 0 })), serie_diaria: [], llm_por_modelo: [] },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    const { getByTestId } = await render();
    for (const nome of ["llm", "infosimples", "d4sign", "google_maps"]) {
      expect(getByTestId(`custos-card-${nome}`)).toBeTruthy();
    }
  });

  it("shows real totals + per-model breakdown once data loads", async () => {
    mockUseCustos.mockReturnValue({ data: CUSTOS, error: null, showSkeleton: false, isRefreshing: false });
    const { getByTestId, getByText } = await render();
    expect(getByTestId("custos-total").textContent).toContain("42");
    expect(getByText("claude-sonnet-5")).toBeTruthy();
  });

  it("never shows d4sign/google_maps as a confirmed zero cost — untracked reads as a dash, not R$ 0,00", async () => {
    mockUseCustos.mockReturnValue({ data: CUSTOS, error: null, showSkeleton: false, isRefreshing: false });
    const { getByTestId } = await render();
    expect(getByTestId("custos-card-d4sign").textContent).toContain("—");
    expect(getByTestId("custos-card-d4sign").textContent).not.toContain("R$ 0,00");
  });

  it("flags FX-pending totals instead of silently understating them", async () => {
    mockUseCustos.mockReturnValue({
      data: { ...CUSTOS, fx_pendente: true },
      error: null,
      showSkeleton: false,
      isRefreshing: false,
    });
    const { getByText } = await render();
    expect(getByText(/cota[çc][ãa]o ptax/i)).toBeTruthy();
  });
});
