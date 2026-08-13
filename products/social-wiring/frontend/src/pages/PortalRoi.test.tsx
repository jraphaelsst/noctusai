/**
 * PortalRoi.test.tsx — the four required states (PROJECT.md §3.5) plus the
 * page's non-negotiable rendering rule: `investimento: null` never renders
 * as a currency zero, and a portal with leads + no spend gets a visible
 * "Registrar investimento" affordance.
 *
 * `@noctusai/lib/design-system` is stubbed at the test boundary (same
 * pattern as `IgDMs.test.tsx`/`WhatsAppChatWindow.test.tsx`) — the real
 * barrel transitively imports `useAIOutputFor` → `@noctusai/seed/infra`,
 * which throws at module-load time without `VITE_SUPABASE_URL`.
 * `@noctusai/seed/infra` is stubbed too — `usePortalRoi.ts` imports its
 * `api` client at module scope, and importing the REAL module (even via
 * `vi.importActual`, to keep the real formatters/types) transitively
 * constructs the real Supabase client and throws the same way.
 * `CampanhaManagerDialog` is stubbed too — its own CRUD/409 behavior is
 * covered by `CampanhaManagerDialog.test.tsx`; this file only asserts the
 * page wires the right (`origemId`, `origemLabel`) into it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockUsePortalRoiResumo = vi.fn();

vi.mock("@/hooks/usePortalRoi", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/usePortalRoi")>(
    "@/hooks/usePortalRoi",
  );
  return { ...actual, usePortalRoiResumo: mockUsePortalRoiResumo };
});

vi.mock("@noctusai/lib/design-system", () => ({
  StatTile: (props: any) => (
    <div data-testid="stat-tile" data-label={props.label}>
      {String(props.value)}
    </div>
  ),
  StatTileRow: (props: any) => <div data-testid="stat-tile-row">{props.children}</div>,
  // `@/components/ui/skeleton` re-exports the real Skeleton from this same
  // barrel — mocking the barrel without this entry makes `<Skeleton>`
  // resolve to `undefined` (the loading state renders it).
  Skeleton: (props: any) => <div data-testid="skeleton" className={props.className} />,
}));

let lastManagerProps: any = null;
vi.mock("@/components/portal-roi/CampanhaManagerDialog", () => ({
  CampanhaManagerDialog: (props: any) => {
    lastManagerProps = props;
    return props.open ? <div data-testid="campanha-manager-stub" /> : null;
  },
}));

function portal(overrides: Partial<any> = {}) {
  return {
    origem_id: "o1",
    slug: "senseys",
    label: "Senseys",
    categoria: "portal",
    investimento: null,
    total_leads: 3728,
    total_vendas: 0,
    valor_vendas: 0,
    cpl: null,
    roi: null,
    taxa_conversao: null,
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: PortalRoi } = await import("./PortalRoi");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(PortalRoi)) };
}

beforeEach(() => {
  vi.clearAllMocks();
  lastManagerProps = null;
});

describe("PortalRoi — loading", () => {
  it("gates on isPending || isFetching, never isLoading (no isEmpty flash mid-refetch)", async () => {
    mockUsePortalRoiResumo.mockReturnValue({
      isPending: false,
      isFetching: true,
      isError: false,
      data: { periodo: null, totais: {}, portais: [] },
      refetch: vi.fn(),
    });
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("portal-roi-loading")).toBeTruthy();
    expect(queryByTestId("portal-row")).toBeNull();
  });
});

describe("PortalRoi — error", () => {
  it("shows the error state with a retry action", async () => {
    const refetch = vi.fn();
    mockUsePortalRoiResumo.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: true,
      data: undefined,
      refetch,
    });
    const { getByText } = await renderPage();
    expect(getByText("Não foi possível carregar os dados de ROI por portal.")).toBeTruthy();
  });
});

describe("PortalRoi — empty (no lead_sources at all)", () => {
  it("shows the empty state, distinct from 'sources with no spend'", async () => {
    mockUsePortalRoiResumo.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { periodo: null, totais: {}, portais: [] },
      refetch: vi.fn(),
    });
    const { getByText, queryByTestId } = await renderPage();
    expect(getByText("Nenhuma origem de lead configurada ainda.")).toBeTruthy();
    expect(queryByTestId("portal-row")).toBeNull();
  });
});

describe("PortalRoi — success", () => {
  const resumo = {
    periodo: null,
    totais: {
      investimento: null,
      total_leads: 13329,
      total_vendas: 0,
      valor_vendas: 0,
      cpl: null,
      roi: null,
      taxa_conversao: null,
    },
    portais: [
      portal({ origem_id: "o1", label: "Senseys", total_leads: 3728 }),
      portal({
        origem_id: "o2",
        label: "ZAP",
        investimento: 3200,
        cpl: 3.94,
        roi: 12.5,
        taxa_conversao: 4.2,
      }),
    ],
  };

  beforeEach(() => {
    mockUsePortalRoiResumo.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: resumo,
      refetch: vi.fn(),
    });
  });

  it("renders every portal row plus the KPI tile row", async () => {
    const { getAllByTestId } = await renderPage();
    expect(getAllByTestId("portal-row")).toHaveLength(2);
    expect(getAllByTestId("stat-tile-row")).toHaveLength(1);
  });

  it("never renders 'R$ 0,00' for a null investimento — renders the muted dash instead", async () => {
    const { getAllByTestId } = await renderPage();
    const naoInformadoCells = getAllByTestId("nao-informado");
    // Senseys' investimento/cpl/roi/taxa_conversao are all null → 4 dash cells.
    expect(naoInformadoCells.length).toBe(4);
    for (const cell of naoInformadoCells) {
      expect(cell.textContent).toBe("—");
      expect(cell.title).toBe("Não informado");
      // Guard against the exact lying-zero bug §2 fixes one layer down: a
      // null-coerced-to-currency-zero would still be text "R$ 0,00" here.
      expect(cell.textContent).not.toContain("R$");
      expect(cell.textContent).not.toContain("0,00");
    }
  });

  it("shows a visible 'Registrar investimento' CTA on the row with no recorded spend", async () => {
    const { getAllByTestId } = await renderPage();
    const ctas = getAllByTestId("registrar-investimento-btn");
    expect(ctas).toHaveLength(1); // only Senseys (investimento: null)
  });

  it("shows 'Ver lançamentos' (not the CTA) on a row that already has spend", async () => {
    const { getAllByTestId } = await renderPage();
    expect(getAllByTestId("ver-lancamentos-btn")).toHaveLength(1); // only ZAP
  });

  it("opens the manager dialog scoped to the clicked portal's origem", async () => {
    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [cta] = getAllByTestId("registrar-investimento-btn");
    fireEvent.click(cta);
    expect(lastManagerProps).toMatchObject({ open: true, origemId: "o1", origemLabel: "Senseys" });
  });
});
