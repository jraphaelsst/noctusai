/**
 * Corretores.test.tsx — Leads "Corretores" subtab.
 *
 * Regression coverage for leads-p0-frontend-ux finding #2: the folded
 * "outros" remainder row (`_reference_by_dimension`'s literal `"outros"`
 * key) used to be clickable like any other row — toggling `corretor_id`
 * with the LITERAL string "outros" 422s every endpoint that shares
 * `get_lead_filters` (a typed-UUID param). Asserts it now renders
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
const mockUseLeadsSummary = vi.fn();
const mockUseLeadsTimeseries = vi.fn();
vi.mock("@/hooks/useLeadsAnalytics", () => ({
  useLeadsByDimension: mockUseLeadsByDimension,
  useLeadsSummary: mockUseLeadsSummary,
  useLeadsTimeseries: mockUseLeadsTimeseries,
}));

vi.mock("@noctusai/lib/design-system", () => ({
  AreaChart: () => <div data-testid="area-chart" />,
  BarChart: () => <div data-testid="bar-chart" />,
  DonutChart: () => <div data-testid="donut-chart" />,
  // Replicates the REAL ChartCard's state priority (loading > error >
  // isEmpty > children — see seed/lib/frontend/src/design-system/charts/
  // ChartCard.tsx) instead of always rendering `children` regardless of the
  // `loading`/`error`/`isEmpty` props. A mock that ignores those props can
  // never fail when a page miscomputes them — which is exactly why these
  // three test files could not catch the 2026-07-21/22 "Sem dados" incident
  // (`KB § PATTERNS/frontend/lying-loading-state.md`). Emits a distinguishable
  // `data-chart-state` marker per branch, keyed by `data-chart-title` so a
  // page with multiple ChartCards can be asserted on individually.
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

function makeQuery(overrides: Partial<any> = {}) {
  return { data: undefined, isPending: false, isFetching: false, isError: false, ...overrides };
}

const BUCKETS = [
  { key: "corretor-1-uuid", label: "Ana", cor: "#111", total: 30, share_pct: 30, novos: 15, retornos: 15, variacao_pct: null },
  { key: "outros", label: "Outros", cor: null, total: 70, share_pct: 70, novos: 35, retornos: 35, variacao_pct: null },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockUseLeadsFilters.mockReturnValue({
    filters: { corretor_id: [] as string[] },
    toggleMulti: mockToggleMulti,
    clearAll: mockClearAll,
  });
  mockUseLeadsByDimension.mockReturnValue(makeQuery({ data: { dim: "corretor", total: 30, buckets: BUCKETS } }));
  mockUseLeadsSummary.mockReturnValue(makeQuery({ data: { total: 100 } }));
  mockUseLeadsTimeseries.mockReturnValue(makeQuery({ data: { grain: "mes", split: "corretor", series_meta: [], points: [] } }));
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Corretores } = await import("./Corretores");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Corretores)), fireEvent: rtl.fireEvent };
}

describe("Corretores — 'outros' row", () => {
  it("does NOT toggle any filter when clicked (the fold is an aggregate, not a filterable value)", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("leads-corretor-row-outros"));
    expect(mockToggleMulti).not.toHaveBeenCalled();
  });

  it("still toggles a real corretor row with its actual id", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("leads-corretor-row-corretor-1-uuid"));
    expect(mockToggleMulti).toHaveBeenCalledWith("corretor_id", "corretor-1-uuid");
  });

  it("surfaces the unattributed count next to the donut", async () => {
    const { container } = await renderPage();
    expect(container.textContent).toMatch(/30 de 100 leads com corretor identificado/i);
  });
});

describe("Corretores — table error recovery", () => {
  it("renders a 'Limpar filtros' action next to the table error and wires it to clearAll", async () => {
    mockUseLeadsByDimension.mockReturnValue(makeQuery({ isError: true }));
    const { getByTestId, fireEvent } = await renderPage();

    const errorBlock = getByTestId("leads-corretores-table-error");
    const clearButton = getByTestId("leads-error-clear-filters");
    expect(errorBlock.contains(clearButton)).toBe(true);

    fireEvent.click(clearButton);
    expect(mockClearAll).toHaveBeenCalledTimes(1);
  });
});

// ─── Regression: 2026-07-21/22 "Sem dados" over 28 brokers / 12,177 leads ──
//
// `ChartCard`'s priority is loading > error > empty. `Corretores.tsx` gates
// the "Ranking de corretores" card on `byDimQ.isPending && !byDimQ.data` —
// the two-signal fix (`KB § PATTERNS/frontend/lying-loading-state.md`). The
// buggy predecessor gated on the bare `.isLoading` field
// (`isPending && isFetching`), which goes false the instant a fetch is not
// actively in flight even though no data has ever resolved (e.g. between
// retry attempts) — the empty branch then won.
describe("Corretores — ChartCard loading state (regression)", () => {
  const RANKING_TITLE = "Ranking de corretores";

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
    const resolved = { dim: "corretor", total: 30, buckets: BUCKETS };
    mockUseLeadsByDimension.mockReturnValue(makeQuery({ data: resolved }));
    const React = (await import("react")).default;
    const { default: Corretores } = await import("./Corretores");
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
    rerender(React.createElement(Corretores));

    card = container.querySelector(`[data-chart-title="${RANKING_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("success");
    expect(card?.querySelector('[data-testid="bar-chart"]')).toBeTruthy();
    expect(card?.textContent).not.toMatch(/Sem dados/i);
  });
});
