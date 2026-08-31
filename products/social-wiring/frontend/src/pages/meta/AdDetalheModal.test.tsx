/**
 * AdDetalheModal.test.tsx — one ad's own live Meta metrics modal.
 *
 * Covers: loading state (isPending/isFetching, never isLoading — the "no
 * lying loading state" contract, verified against the REAL MetricCard so
 * this actually exercises that gate rather than a fake), error state (a
 * retry that calls the right refetch), and success (KPI tiles render from
 * mocked `/insights/compare` + `/insights/series` data, including that
 * leads are summed via `rowLeads` so BOTH `actions["lead"]` and
 * `actions["onsite_conversion.lead"]` rows count).
 *
 * Consumes the REAL `MetricCard` (pure, no heavy deps) — every other
 * primitive (Dialog/Card/Badge/recharts, the data hooks, `./adsShared`) is
 * fully mocked (no `importOriginal`: the real `./adsShared` + the real
 * `@/hooks/useMetaAds` both transitively pull in `@noctusai/seed/infra`'s
 * whole design-system barrel, which needs a lucide-react surface far wider
 * than this file cares about — mirrors the AdsCampanhas.test.tsx /
 * LeadgenWebhookCard.test.tsx full-mock convention exactly).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { formatCents } from "@/lib/formatCurrency";
import { formatNumber } from "@/lib/formatNumber";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

interface FakeAdsObject {
  object_id: string;
  level: string;
  parent_id: string | null;
  name: string | null;
  status: string | null;
  effective_status: string | null;
  daily_budget_cents: number | null;
  optimization_goal: string | null;
  creative_id: string | null;
  creative_thumbnail_url: string | null;
}

const mockUseAdsInsightsCompare = vi.fn();
const mockUseAdsInsightsSeries = vi.fn();

vi.mock("@/hooks/useMetaAds", () => ({
  useAdsInsightsCompare: (...args: unknown[]) => mockUseAdsInsightsCompare(...args),
  useAdsInsightsSeries: (...args: unknown[]) => mockUseAdsInsightsSeries(...args),
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open, onOpenChange }: any) =>
    open ? (
      <div data-testid="dialog">
        <button data-testid="dialog-close" onClick={() => onOpenChange(false)} />
        {children}
      </div>
    ) : null,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, ...p }: any) => <span {...p}>{children}</span>,
}));
vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("lucide-react", () => ({
  DollarSign: () => null,
  Eye: () => null,
  MousePointerClick: () => null,
  Target: () => null,
  Users: () => null,
}));
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  CartesianGrid: () => null,
  Line: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

// Fully mocked (no importOriginal — see file header). `pct`/`rowLeads`/
// `statusVariant` are re-implemented faithfully here: they're one-liners,
// and the leads dual-action-key contract (`rowLeads`) is exactly what this
// file needs to verify, so it must match the real semantics precisely.
vi.mock("./adsShared", () => ({
  useDateRange: () => ({
    preset: "28d",
    setPreset: vi.fn(),
    range: { since: "2026-08-01", until: "2026-08-28" },
  }),
  DateRangeSelect: () => <div data-testid="date-range-select" />,
  AdsError: ({ message, onRetry }: any) => (
    <div data-testid="ads-error">
      {message}
      {onRetry && <button onClick={onRetry}>Tentar de novo</button>}
    </div>
  ),
  pct: (curr: number, prev: number) => (prev ? ((curr - prev) / prev) * 100 : null),
  rowLeads: (row: any) => row.actions?.["lead"] ?? row.actions?.["onsite_conversion.lead"] ?? 0,
  statusVariant: (effective?: string | null) => {
    const s = (effective ?? "").toUpperCase();
    if (s === "ACTIVE") return { label: "Ativa", cls: "active" };
    if (s === "PAUSED") return { label: "Pausada", cls: "paused" };
    return { label: effective ?? "—", cls: "muted" };
  },
}));

const AD: FakeAdsObject = {
  object_id: "ad-1",
  level: "ad",
  parent_id: "adset-1",
  name: "ONE10528",
  status: "ACTIVE",
  effective_status: "ACTIVE",
  daily_budget_cents: null,
  optimization_goal: null,
  creative_id: "creative-1",
  creative_thumbnail_url: "https://example.com/thumb.jpg",
};

const CURRENT_TOTALS = { spend_cents: 100_000, impressions: 5_000, reach: 4_000, clicks: 300 };
const PREVIOUS_TOTALS = { spend_cents: 80_000, impressions: 4_000, reach: 3_500, clicks: 250 };

// Two rows: one uses `actions["lead"]`, the other `actions["onsite_conversion.lead"]`
// — rowLeads() must sum BOTH, matching what the account actually sends.
const CURRENT_SERIES_ROWS = [
  {
    date: "2026-08-10", spend_cents: 4000, impressions: 2000, reach: 1800, clicks: 120,
    cpc_cents: null, cpm_cents: null, ctr: null,
    actions: { lead: 1 }, action_values: {}, breakdown: {},
  },
  {
    date: "2026-08-11", spend_cents: 6000, impressions: 3000, reach: 2200, clicks: 180,
    cpc_cents: null, cpm_cents: null, ctr: null,
    actions: { "onsite_conversion.lead": 2 }, action_values: {}, breakdown: {},
  },
];
const PREVIOUS_SERIES_ROWS = [
  {
    date: "2026-07-04", spend_cents: 8000, impressions: 4000, reach: 3500, clicks: 250,
    cpc_cents: null, cpm_cents: null, ctr: null,
    actions: { lead: 2 }, action_values: {}, breakdown: {},
  },
];
// curLeads = 1 + 2 = 3; prevLeads = 2.

function setDefaults() {
  mockUseAdsInsightsCompare.mockReturnValue({
    data: { current: CURRENT_TOTALS, previous: PREVIOUS_TOTALS, deltas: {} },
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  });
  mockUseAdsInsightsSeries.mockImplementation((_id: string, _level: string, since: string) => {
    const rows = since === "2026-08-01" ? CURRENT_SERIES_ROWS : PREVIOUS_SERIES_ROWS;
    return { data: { object_id: "ad-1", level: "ad", rows }, isPending: false, isFetching: false, isError: false, refetch: vi.fn() };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  setDefaults();
});

async function renderModal(onClose = vi.fn()) {
  const { render, screen } = await import("@testing-library/react");
  const { AdDetalheModal } = await import("./AdDetalheModal");
  const utils = render(<AdDetalheModal ad={AD} currency="BRL" onClose={onClose} />);
  return { ...utils, screen, onClose };
}

/** Locate a MetricCard's rendered text block by its label. */
function tileText(screen: typeof import("@testing-library/react").screen, label: string): string {
  const labelEl = screen.getByText(label);
  const card = labelEl.closest(".p-5");
  return card?.textContent ?? "";
}

describe("AdDetalheModal", () => {
  it("renders the ad's own name, status, and object_id in the header", async () => {
    const { screen } = await renderModal();
    expect(screen.getByText("ONE10528")).toBeTruthy();
    expect(screen.getByText("ad-1")).toBeTruthy();
    expect(screen.getByText("Ativa")).toBeTruthy();
  });

  it("gates KPI loading on isPending/isFetching — never isLoading — so a background refetch shows the loading placeholder, not a stale/empty value", async () => {
    mockUseAdsInsightsCompare.mockReturnValue({
      data: undefined,
      isPending: false, // mimics TanStack v5 mid-refetch: isLoading would be false here too
      isFetching: true,
      isError: false,
      refetch: vi.fn(),
    });
    const { screen } = await renderModal();
    // MetricCard's real loading branch renders "—", never the formatted
    // value nor a "sem dados" empty state.
    expect(tileText(screen, "Gasto")).toContain("—");
  });

  it("shows the KPI error state with a retry that calls the compare refetch", async () => {
    const refetch = vi.fn();
    mockUseAdsInsightsCompare.mockReturnValue({
      data: undefined, isPending: false, isFetching: false, isError: true, refetch,
    });
    const { screen } = await renderModal();
    const { fireEvent } = await import("@testing-library/react");
    expect(screen.getByTestId("ads-error")).toBeTruthy();
    fireEvent.click(screen.getByText("Tentar de novo"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("renders spend/impressions/reach/clicks straight from /insights/compare", async () => {
    const { screen } = await renderModal();
    expect(tileText(screen, "Gasto")).toContain(formatCents(CURRENT_TOTALS.spend_cents, "BRL"));
    expect(tileText(screen, "Impressões")).toContain(formatNumber(CURRENT_TOTALS.impressions));
    expect(tileText(screen, "Alcance")).toContain(formatNumber(CURRENT_TOTALS.reach));
    expect(tileText(screen, "Cliques")).toContain(formatNumber(CURRENT_TOTALS.clicks));
  });

  it("sums leads via rowLeads across BOTH actions['lead'] and actions['onsite_conversion.lead'] — never just one key", async () => {
    const { screen } = await renderModal();
    // 1 (actions.lead) + 2 (actions['onsite_conversion.lead']) = 3
    expect(tileText(screen, "Leads")).toContain(formatNumber(3));
  });

  it("derives Custo/lead, Custo por clique, CPM and CTR from the same numbers — and only when they're meaningful", async () => {
    const { screen } = await renderModal();
    const cpl = Math.round(CURRENT_TOTALS.spend_cents / 3); // curLeads = 3
    const cpc = Math.round(CURRENT_TOTALS.spend_cents / CURRENT_TOTALS.clicks);
    const cpm = Math.round((CURRENT_TOTALS.spend_cents / CURRENT_TOTALS.impressions) * 1000);
    expect(tileText(screen, "Custo/lead")).toContain(formatCents(cpl, "BRL"));
    expect(tileText(screen, "Custo por clique")).toContain(formatCents(cpc, "BRL"));
    expect(tileText(screen, "CPM")).toContain(formatCents(cpm, "BRL"));
    expect(screen.getByText("CTR")).toBeTruthy();
  });

  it("chart: shows the empty state when the series has no rows for the window", async () => {
    mockUseAdsInsightsSeries.mockImplementation((_id: string, _level: string, since: string) => ({
      data: { object_id: "ad-1", level: "ad", rows: since === "2026-08-01" ? [] : PREVIOUS_SERIES_ROWS },
      isPending: false, isFetching: false, isError: false, refetch: vi.fn(),
    }));
    const { screen } = await renderModal();
    expect(screen.getByText("Nenhum dado no período.")).toBeTruthy();
    expect(screen.queryByTestId("line-chart")).toBeNull();
  });

  it("chart: renders the spend line when the series has rows", async () => {
    const { screen } = await renderModal();
    expect(screen.getByTestId("line-chart")).toBeTruthy();
  });

  it("chart: shows a chart-scoped error with retry, independent of the KPI section", async () => {
    const refetch = vi.fn();
    mockUseAdsInsightsSeries.mockImplementation((_id: string, _level: string, since: string) => {
      if (since === "2026-08-01") {
        return { data: undefined, isPending: false, isFetching: false, isError: true, refetch };
      }
      return { data: { object_id: "ad-1", level: "ad", rows: PREVIOUS_SERIES_ROWS }, isPending: false, isFetching: false, isError: false, refetch: vi.fn() };
    });
    const { screen } = await renderModal();
    const { fireEvent } = await import("@testing-library/react");
    // Both the KPI-side AdsError instances are stand-ins from the mock — the
    // chart's carries its own message + its own refetch.
    fireEvent.click(screen.getAllByText("Tentar de novo")[0]);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the Dialog reports onOpenChange(false) (Escape / backdrop / close button, per the Radix Dialog contract)", async () => {
    const onClose = vi.fn();
    const { screen } = await renderModal(onClose);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(screen.getByTestId("dialog-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
