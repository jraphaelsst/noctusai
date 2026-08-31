/**
 * Origens.test.tsx — Leads "Origens" subtab.
 *
 * Regression coverage for leads-p0-frontend-ux finding #1: clicking a
 * bucket row used to emit the source SLUG (the `by-dimension` bucket key)
 * as `origem_id`, a typed-UUID filter param — 422ing every endpoint that
 * shares `get_lead_filters`. Asserts the row click now resolves slug->id
 * via `useLeadSources()` before toggling the filter, AND that the folded
 * "outros" remainder row (never a real dimension value) renders
 * non-interactive rather than emitting the literal string "outros".
 *
 * Mock strategy mirrors Configuracao.test.tsx — hooks are `vi.fn()`s
 * configured per test, `@noctusai/lib/design-system` is stubbed (the real
 * barrel throws at module-load without VITE_SUPABASE_URL).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockToggleMulti = vi.fn();
const mockClearAll = vi.fn();
const mockUseLeadsFilters = vi.fn();
vi.mock("@/hooks/useLeadsFilters", () => ({
  useLeadsFilters: mockUseLeadsFilters,
}));

const mockUseLeadSources = vi.fn();
vi.mock("@/hooks/useLeadsSources", () => ({
  useLeadSources: mockUseLeadSources,
}));

const mockUseLeadsByDimension = vi.fn();
const mockUseLeadsSummary = vi.fn();
const mockUseLeadsTimeseries = vi.fn();
vi.mock("@/hooks/useLeadsAnalytics", () => ({
  useLeadsByDimension: mockUseLeadsByDimension,
  useLeadsSummary: mockUseLeadsSummary,
  useLeadsTimeseries: mockUseLeadsTimeseries,
}));

// ─── Design-system stub ──────────────────────────────────────────────────────

vi.mock("@noctusai/lib/design-system", () => ({
  AreaChart: () => <div data-testid="area-chart" />,
  // Replicates the REAL ChartCard's state priority (loading > error >
  // isEmpty > children — see seed/lib/frontend/src/design-system/charts/
  // ChartCard.tsx) instead of always rendering `children` regardless of the
  // `loading`/`error`/`isEmpty` props. A mock that ignores those props can
  // never fail when a page miscomputes them — which is exactly why this
  // test file could not catch the 2026-07-21/22 "Sem dados" incident
  // (`KB § PATTERNS/frontend/lying-loading-state.md`). Emits a
  // distinguishable `data-chart-state` marker.
  ChartCard: ({ children, title, loading, error, isEmpty }: any) => {
    const state = loading ? "loading" : error ? "error" : isEmpty ? "empty" : "success";
    return (
      <div data-testid="chart-card" data-chart-title={title} data-chart-state={state}>
        <p>{title}</p>
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

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeQuery(overrides: Partial<any> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    ...overrides,
  };
}

const SOURCES = [
  { id: "uuid-viva-real", org_id: "o1", slug: "viva-real", label: "Viva Real", categoria: "portal", cor: "#111", ativo: true, ordem: 1, created_at: "", updated_at: null },
  { id: "uuid-site", org_id: "o1", slug: "site", label: "Site", categoria: "direto", cor: "#222", ativo: true, ordem: 2, created_at: "", updated_at: null },
];

const BUCKETS = [
  { key: "viva-real", label: "Viva Real", cor: "#111", total: 40, share_pct: 40, novos: 20, retornos: 20, variacao_pct: null },
  { key: "site", label: "Site", cor: "#222", total: 20, share_pct: 20, novos: 10, retornos: 10, variacao_pct: null },
  { key: "outros", label: "Outros", cor: null, total: 40, share_pct: 40, novos: 20, retornos: 20, variacao_pct: null },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockUseLeadsFilters.mockReturnValue({
    filters: { origem_id: [] as string[] },
    toggleMulti: mockToggleMulti,
    clearAll: mockClearAll,
  });
  mockUseLeadSources.mockReturnValue(makeQuery({ data: SOURCES }));
  mockUseLeadsByDimension.mockReturnValue(makeQuery({ data: { dim: "origem", total: 100, buckets: BUCKETS } }));
  mockUseLeadsSummary.mockReturnValue(makeQuery({ data: { total: 100 } }));
  mockUseLeadsTimeseries.mockReturnValue(makeQuery({ data: { grain: "mes", split: "origem", series_meta: [], points: [] } }));
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Origens } = await import("./Origens");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Origens)), fireEvent: rtl.fireEvent };
}

describe("Origens — drill-in click", () => {
  it("toggles the filter with the source UUID, never the raw slug bucket key", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("leads-origem-row-viva-real"));

    expect(mockToggleMulti).toHaveBeenCalledTimes(1);
    const [key, value] = mockToggleMulti.mock.calls[0];
    expect(key).toBe("origem_id");
    expect(value).toBe("uuid-viva-real");
    expect(value).not.toBe("viva-real");
  });

  it("does NOT toggle any filter when the folded 'outros' row is clicked", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("leads-origem-row-outros"));
    expect(mockToggleMulti).not.toHaveBeenCalled();
  });

  it("shows the attribution note when the by-dimension total is lower than the grand total", async () => {
    const { getByTestId } = await renderPage();
    const note = getByTestId("leads-origens-attribution");
    expect(note.textContent).toMatch(/100 de 100 leads com origem identificada/i);
  });
});

describe("Origens — table error recovery", () => {
  it("renders a 'Limpar filtros' action next to the table error and wires it to clearAll", async () => {
    mockUseLeadsByDimension.mockReturnValue(makeQuery({ isError: true }));
    const { getByTestId, fireEvent } = await renderPage();

    const errorBlock = getByTestId("leads-origens-table-error");
    const clearButton = getByTestId("leads-error-clear-filters");
    expect(errorBlock.contains(clearButton)).toBe(true);

    fireEvent.click(clearButton);
    expect(mockClearAll).toHaveBeenCalledTimes(1);
  });
});

// ─── Regression: 2026-07-21/22 "Sem dados" over 28 brokers / 12,177 leads ──
//
// `ChartCard`'s priority is loading > error > empty. `Origens.tsx` gates
// the "Evolução por origem" card on `timeseriesQ.isPending && !timeseriesQ.data`
// — the two-signal fix (`KB § PATTERNS/frontend/lying-loading-state.md`). The
// buggy predecessor gated on the bare `.isLoading` field
// (`isPending && isFetching`), which goes false the instant a fetch is not
// actively in flight even though no data has ever resolved (e.g. between
// retry attempts) — the empty branch then won.
describe("Origens — ChartCard loading state (regression)", () => {
  const EVOLUCAO_TITLE = "Evolução por origem";
  const TIMESERIES_DATA = {
    grain: "mes",
    split: "origem",
    series_meta: [{ key: "viva-real", label: "Viva Real", cor: "#111" }],
    points: [{ label: "Jan", series: { "viva-real": 10 } }],
  };

  it("Mode A guard: never shows the empty state while data has not resolved (isPending true, isFetching false, no data)", async () => {
    mockUseLeadsTimeseries.mockReturnValue(
      makeQuery({ isPending: true, isFetching: false, data: undefined }),
    );
    const { container } = await renderPage();

    const card = container.querySelector(`[data-chart-title="${EVOLUCAO_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("loading");
    expect(card?.textContent).not.toMatch(/Sem dados/i);
  });

  it("Mode B guard: keeps the chart mounted through a real background-refetch transition (data resolved, then fetching again)", async () => {
    mockUseLeadsTimeseries.mockReturnValue(makeQuery({ data: TIMESERIES_DATA }));
    const React = (await import("react")).default;
    const { default: Origens } = await import("./Origens");
    const { container, rerender } = await renderPage();

    let card = container.querySelector(`[data-chart-title="${EVOLUCAO_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("success");
    expect(card?.querySelector('[data-testid="area-chart"]')).toBeTruthy();

    // Background refetch starts on top of already-resolved data — the exact
    // TanStack v5 state a live refetch produces (`isPending: false` because
    // data has resolved once; `isFetching: true` for the request in flight).
    mockUseLeadsTimeseries.mockReturnValue(
      makeQuery({ isFetching: true, data: TIMESERIES_DATA }),
    );
    rerender(React.createElement(Origens));

    card = container.querySelector(`[data-chart-title="${EVOLUCAO_TITLE}"]`);
    expect(card?.getAttribute("data-chart-state")).toBe("success");
    expect(card?.querySelector('[data-testid="area-chart"]')).toBeTruthy();
    expect(card?.textContent).not.toMatch(/Sem dados/i);
  });
});
