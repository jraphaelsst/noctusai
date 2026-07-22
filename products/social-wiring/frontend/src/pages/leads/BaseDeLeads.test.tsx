/**
 * BaseDeLeads.test.tsx — Leads "Base de Leads" subtab.
 *
 * Focused coverage for the error-recovery affordance added alongside the
 * URL-filter-validation fix (leads-url-filter-validation): even with
 * hydration validated, a VALID-shaped filter (e.g. a UUID for a source
 * that's since been deleted) can still fail at request time. Asserts the
 * "Limpar filtros" action renders next to the bare error message and wires
 * to `clearAll`.
 *
 * Mock strategy mirrors Origens.test.tsx / Corretores.test.tsx — hooks are
 * `vi.fn()`s configured per test; `@noctusai/lib/design-system` is stubbed
 * (the real barrel throws at module-load without VITE_SUPABASE_URL);
 * `LeadFormDialog`/`LeadDetailDrawer` are stubbed out entirely (irrelevant
 * to this slice).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { LeadsFilters } from "@/hooks/useLeadsFilters";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const EMPTY_FILTERS: LeadsFilters = {
  de: null,
  ate: null,
  ano: [],
  mes: [],
  origem_id: [],
  corretor_id: [],
  tipo: [],
  tier: [],
  empreendimento: [],
  regiao: [],
  needs_review: null,
  q: null,
};

const mockSetNeedsReview = vi.fn();
const mockClearAll = vi.fn();
const mockUseLeadsFilters = vi.fn();
vi.mock("@/hooks/useLeadsFilters", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useLeadsFilters")>(
    "@/hooks/useLeadsFilters",
  );
  return { ...actual, useLeadsFilters: mockUseLeadsFilters };
});

const mockUseLeadsList = vi.fn();
const mockUseLeadMutations = vi.fn();
vi.mock("@/hooks/useLeads", () => ({
  useLeadsList: mockUseLeadsList,
  useLeadMutations: mockUseLeadMutations,
}));

vi.mock("@noctusai/lib/design-system", () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

vi.mock("./components/LeadFormDialog", () => ({
  LeadFormDialog: () => null,
}));
vi.mock("./components/LeadDetailDrawer", () => ({
  LeadDetailDrawer: () => null,
}));

function makeQuery(overrides: Partial<any> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseLeadsFilters.mockReturnValue({
    filters: EMPTY_FILTERS,
    setNeedsReview: mockSetNeedsReview,
    clearAll: mockClearAll,
  });
  mockUseLeadsList.mockReturnValue(makeQuery());
  mockUseLeadMutations.mockReturnValue({
    create: { mutate: vi.fn() },
    update: { mutate: vi.fn() },
    remove: { mutate: vi.fn() },
  });
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: BaseDeLeads } = await import("./BaseDeLeads");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(BaseDeLeads)), fireEvent: rtl.fireEvent };
}

describe("BaseDeLeads — table error recovery", () => {
  it("renders a 'Limpar filtros' action next to the bare error message and wires it to clearAll", async () => {
    mockUseLeadsList.mockReturnValue(
      makeQuery({ isError: true, error: new Error("[500] boom") }),
    );
    const { getByTestId, fireEvent } = await renderPage();

    const errorBlock = getByTestId("leads-table-error");
    const clearButton = getByTestId("leads-error-clear-filters");
    expect(errorBlock.contains(clearButton)).toBe(true);

    fireEvent.click(clearButton);
    expect(mockClearAll).toHaveBeenCalledTimes(1);
  });
});
