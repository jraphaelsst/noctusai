/**
 * Lotes.test.tsx — the four required states (loading/error/empty/success)
 * plus the loading-state contract (CLAUDE.md §1 / EDICAO-FOTOS-CONTRACT.md
 * §9): a background refetch (`isRefreshing`) must show the "Atualizando…"
 * indicator WITHOUT swapping the list for a skeleton — never a lying
 * loading state.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseLotes = vi.fn();

vi.mock("@/hooks/useEdicaoFotos", () => ({
  useLotes: (...a: any[]) => mockUseLotes(...a),
}));

function lote(overrides: Partial<any> = {}) {
  return {
    id: "l1",
    nome: "Apto 302",
    criado_em: "2026-09-15T12:00:00Z",
    imovel: null,
    velocidade: "urgente",
    estado_agregado: "aguardando_revisao",
    total_fotos: 10,
    fotos_decididas: 4,
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Lotes } = await import("./Lotes");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(MemoryRouter, null, React.createElement(Lotes))),
    fireEvent: rtl.fireEvent,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Lotes — loading", () => {
  it("shows the skeleton grid, never the list, while showSkeleton is true", async () => {
    mockUseLotes.mockReturnValue({
      lotes: [],
      total: 0,
      showSkeleton: true,
      isRefreshing: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByTestId, queryByText } = await renderPage();

    expect(getByTestId("lotes-loading")).toBeTruthy();
    expect(queryByText("Nenhum lote ainda.")).toBeNull();
  });
});

describe("Lotes — error", () => {
  it("shows the error state with a retry that calls refetch", async () => {
    const refetch = vi.fn();
    mockUseLotes.mockReturnValue({
      lotes: [],
      total: 0,
      showSkeleton: false,
      isRefreshing: false,
      error: new Error("boom"),
      refetch,
    });
    const { getByText, fireEvent } = await renderPage();

    expect(getByText("Não foi possível carregar os lotes.")).toBeTruthy();
    fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe("Lotes — empty", () => {
  it("shows the empty state with a Novo lote CTA when there are zero batches", async () => {
    mockUseLotes.mockReturnValue({
      lotes: [],
      total: 0,
      showSkeleton: false,
      isRefreshing: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage();

    expect(getByTestId("lotes-empty")).toBeTruthy();
  });
});

describe("Lotes — success", () => {
  it("renders a card per lote with its status badge and decided/total count", async () => {
    mockUseLotes.mockReturnValue({
      lotes: [lote(), lote({ id: "l2", nome: "Casa 10", estado_agregado: "com_falhas" })],
      total: 2,
      showSkeleton: false,
      isRefreshing: false,
      error: null,
      refetch: vi.fn(),
    });
    const { getByTestId, getByText } = await renderPage();

    const cardL1 = getByTestId("lote-card-l1");
    const cardL2 = getByTestId("lote-card-l2");
    expect(cardL1).toBeTruthy();
    expect(cardL2).toBeTruthy();
    expect(getByText("Aguardando revisão")).toBeTruthy();
    expect(getByText("Com falhas")).toBeTruthy();
    expect(cardL1.textContent).toContain("4/10");
    expect(cardL1.textContent).toContain("40%");
  });

  it("shows a non-blocking Atualizando indicator during a background refetch — never a skeleton over live data", async () => {
    mockUseLotes.mockReturnValue({
      lotes: [lote()],
      total: 1,
      showSkeleton: false,
      isRefreshing: true,
      error: null,
      refetch: vi.fn(),
    });
    const { getByText, queryByTestId } = await renderPage();

    expect(getByText("Atualizando…")).toBeTruthy();
    expect(queryByTestId("lotes-loading")).toBeNull();
    expect(getByText("Apto 302")).toBeTruthy();
  });
});
