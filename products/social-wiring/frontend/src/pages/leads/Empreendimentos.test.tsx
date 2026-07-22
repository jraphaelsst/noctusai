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
  ChartCard: ({ children, title, subtitle }: any) => (
    <div data-testid="chart-card">
      <p>{title}</p>
      <p>{subtitle}</p>
      {children}
    </div>
  ),
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
