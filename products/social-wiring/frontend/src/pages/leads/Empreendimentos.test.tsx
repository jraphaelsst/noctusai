/**
 * Empreendimentos.test.tsx — Leads "Empreendimentos" subtab.
 *
 * Regression coverage for leads-p0-frontend-ux finding #2: unlike
 * `origem_id`/`corretor_id` (typed UUID params, 422 on the literal
 * "outros"), `empreendimento`/`regiao` are untyped strings — clicking the
 * folded "outros" row used to be accepted as a literal filter value and
 * silently zero every chart (reads as "no data" instead of an error, the
 * more dangerous of the two failure modes). Asserts it renders
 * non-interactive.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockToggleMulti = vi.fn();
const mockClearAll = vi.fn();
const mockUseLeadsFilters = vi.fn();
vi.mock("@/hooks/useLeadsFilters", () => ({
  useLeadsFilters: mockUseLeadsFilters,
}));

const mockUseLeadsByDimension = vi.fn();
vi.mock("@/hooks/useLeadsAnalytics", () => ({
  useLeadsByDimension: mockUseLeadsByDimension,
}));

vi.mock("@noctusai/lib/design-system", () => ({
  BarChart: () => <div data-testid="bar-chart" />,
  // Replicates the REAL ChartCard's state priority (loading > error >
  // isEmpty > children — see seed/lib/frontend/src/design-system/charts/
  // ChartCard.tsx) instead of always rendering `children` regardless of the
  // `loading`/`error`/`isEmpty` props. A mock that ignores those props can
  // never fail when a page miscomputes them — which is exactly why this
  // test file could not catch the 2026-07-21/22 "Sem dados" incident
  // (`KB § PATTERNS/frontend/lying-loading-state.md`). Emits a
  // distinguishable `data-chart-state` marker.
  ChartCard: ({ children, title, subtitle, loading, error, isEmpty }: any) => {
    const state = loading ? "loading" : error ? "error" : isEmpty ? "empty" : "success";
    return (
      <div data-testid="chart-card" data-chart-title={title} data-chart-state={state}>
        <p>{title}</p>
        <p>{subtitle}</p>
        {state === "loading" && <div data-testid="chart-card-skeleton" role="status" aria-label="Carregando" />}
        {state === "error" && <p role="alert">{error}</p>}
        {state === "empty" && <p>Sem dados para o período selecionado.</p>}
        {state === "success" && children}
      </div>
    );
  },
  TableSkeleton: () => <div data-testid="table-skeleton" />,
  formatPercent: (v: number) => `${v}%`,
  formatPercentDelta: (v: number) => `${v}%`,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, "data-testid": dt }: any) => (
    <button onClick={onClick} data-testid={dt}>
      {children}
    </button>
  ),
}));

function makeQuery(overrides: Partial<any> = {}) {
  return { data: undefined, isPending: false, isFetching: false, isError: false, ...overrides };
}

const BUCKETS = [
  { key: "Residencial Alfa", label: "Residencial Alfa", cor: null, total: 50, share_pct: 50, novos: 0, retornos: 0, variacao_pct: null },
  { key: "outros", label: "Outros", cor: null, total: 50, share_pct: 50, novos: 0, retornos: 0, variacao_pct: null },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockUseLeadsFilters.mockReturnValue({
    filters: { empreendimento: [] as string[], regiao: [] as string[] },
    toggleMulti: mockToggleMulti,
    clearAll: mockClearAll,
  });
  mockUseLeadsByDimension.mockReturnValue(
    makeQuery({ data: { dim: "empreendimento", total: 50, buckets: BUCKETS } }),
  );
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Empreendimentos } = await import("./Empreendimentos");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Empreendimentos)), fireEvent: rtl.fireEvent };
}

describe("Empreendimentos — 'outros' row", () => {
  it("does NOT toggle the empreendimento filter with the literal 'outros' value", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("leads-empreendimento-row-outros"));
    expect(mockToggleMulti).not.toHaveBeenCalled();
  });

  it("still toggles a real empreendimento row with its actual value", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("leads-empreendimento-row-Residencial Alfa"));
    expect(mockToggleMulti).toHaveBeenCalledWith("empreendimento", "Residencial Alfa");
  });
});

describe("Empreendimentos — table error recovery", () => {
  it("renders a 'Limpar filtros' action next to the table error and wires it to clearAll", async () => {
    mockUseLeadsByDimension.mockReturnValue(makeQuery({ isError: true }));
    const { getByTestId, fireEvent } = await renderPage();

    const errorBlock = getByTestId("leads-empreendimentos-table-error");
    const clearButton = getByTestId("leads-error-clear-filters");
    expect(errorBlock.contains(clearButton)).toBe(true);

    fireEvent.click(clearButton);
    expect(mockClearAll).toHaveBeenCalledTimes(1);
  });
});

// ─── Regression: 2026-07-21/22 "Sem dados" over 28 brokers / 12,177 leads ──
//
// `ChartCard`'s priority is loading > error > empty. `Empreendimentos.tsx`
// gates the ranking card on `byDimQ.isPending && !byDimQ.data` — the
// two-signal fix (`KB § PATTERNS/frontend/lying-loading-state.md`). The
// buggy predecessor gated on the bare `.isLoading` field
// (`isPending && isFetching`), which goes false the instant a fetch is not
// actively in flight even though no data has ever resolved (e.g. between
// retry attempts) — the empty branch then won.
describe("Empreendimentos — ChartCard loading state (regression)", () => {
  const RANKING_TITLE = "Leads por empreendimento";

  it("Mode A guard: never shows the empty state while data has not resolved (isPending true, isFetching false, no data)", async () => {
    mockUseLeadsByDimension.mockReturnValue(
      makeQuery({ isPending: true, isFetching: false, data: undefined }),
    );
    const { container } = await renderPage();

    const card = container.querySelector(`[data-chart-title="${RANKING_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("loading");
    expect(card?.textContent).not.toMatch(/Sem dados/i);
  });

  it("Mode B guard: keeps the chart mounted through a real background-refetch transition (data resolved, then fetching again)", async () => {
    const resolved = { dim: "empreendimento", total: 50, buckets: BUCKETS };
    mockUseLeadsByDimension.mockReturnValue(makeQuery({ data: resolved }));
    const React = (await import("react")).default;
    const { default: Empreendimentos } = await import("./Empreendimentos");
    const { container, rerender } = await renderPage();

    let card = container.querySelector(`[data-chart-title="${RANKING_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("success");
    expect(card?.querySelector('[data-testid="bar-chart"]')).toBeTruthy();

    // Background refetch starts on top of already-resolved data — the exact
    // TanStack v5 state a live refetch produces (`isPending: false` because
    // data has resolved once; `isFetching: true` for the request in flight).
    mockUseLeadsByDimension.mockReturnValue(
      makeQuery({ isFetching: true, data: resolved }),
    );
    rerender(React.createElement(Empreendimentos));

    card = container.querySelector(`[data-chart-title="${RANKING_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("success");
    expect(card?.querySelector('[data-testid="bar-chart"]')).toBeTruthy();
    expect(card?.textContent).not.toMatch(/Sem dados/i);
  });
});
