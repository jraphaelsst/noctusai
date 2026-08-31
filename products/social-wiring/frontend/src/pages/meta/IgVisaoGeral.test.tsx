/**
 * IgVisaoGeral.test.tsx — Instagram "Visão geral" subtab.
 *
 * Mirrors the retired InstagramInsights.test.tsx conventions: mock every
 * hook + UI primitive, no real TanStack Query provider needed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseMetaContext = vi.fn();
const mockUseIgInsights = vi.fn();
const mockUseIgMedia = vi.fn();
const mockUseIgSnapshots = vi.fn();
const mockUseCaptureIgSnapshot = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useMetaContext: mockUseMetaContext,
  useIgInsights: mockUseIgInsights,
  useIgMedia: mockUseIgMedia,
  useIgSnapshots: mockUseIgSnapshots,
  useCaptureIgSnapshot: mockUseCaptureIgSnapshot,
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt}>{children}</button>
  ),
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ "data-testid": dt }: any) => <div data-testid={dt ?? "skeleton"} />,
}));
vi.mock("@/components/MetricCard", () => ({
  MetricCard: ({ label, value }: any) => <div>{label}: {value}</div>,
}));
vi.mock("recharts", () => ({
  CartesianGrid: () => null,
  Line: () => null,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));
vi.mock("lucide-react", () => ({
  Camera: () => null,
  CircleAlert: () => <span data-testid="icon-alert" />,
  Eye: () => null,
  Grid3x3: () => null,
  Instagram: () => null,
  Loader2: () => <span data-testid="icon-loader" />,
  RefreshCw: () => null,
  Users: () => null,
  UserPlus: () => null,
}));

function makeAccount(overrides: Partial<any> = {}) {
  return {
    id: "17841400000000000",
    username: "minhaempresa",
    name: "Minha Empresa",
    followers_count: 1200,
    follows_count: 300,
    media_count: 42,
    ...overrides,
  };
}

function setDefaults() {
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseMetaContext.mockReturnValue({
    data: { instagram: makeAccount(), pages: [], user: null },
    isPending: false,
    isError: false,
  });
  mockUseIgInsights.mockReturnValue({
    data: { object_id: "x", metrics: { reach: 500, profile_views: 80 }, series: [] },
    isPending: false,
  });
  mockUseIgMedia.mockReturnValue({ data: { media: [] }, isPending: false, isError: false });
  mockUseIgSnapshots.mockReturnValue({ data: { snapshots: [] }, isPending: false, isError: false });
  mockUseCaptureIgSnapshot.mockReturnValue({ mutate: vi.fn(), isPending: false });
}

beforeEach(() => {
  // Clear recorded calls between tests — without this, `mock.calls`
  // accumulates across renders and any assertion on call arguments
  // silently reads a PREVIOUS test's call. (Clears calls only, not the
  // implementations `setDefaults` installs below.)
  vi.clearAllMocks();
  setDefaults();
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: IgVisaoGeral } = await import("./IgVisaoGeral");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(IgVisaoGeral)), fireEvent: rtl.fireEvent };
}

describe("IgVisaoGeral — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-overview-no-account")).toBeTruthy();
  });
});

describe("IgVisaoGeral — context states", () => {
  it("renders a skeleton while context is loading", async () => {
    mockUseMetaContext.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-overview-loading")).toBeTruthy();
  });

  it("renders an error state when context fails", async () => {
    mockUseMetaContext.mockReturnValue({ data: undefined, isPending: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-overview-error")).toBeTruthy();
  });

  it("renders an empty state when there is no IG account", async () => {
    mockUseMetaContext.mockReturnValue({
      data: { instagram: null, pages: [], user: null },
      isPending: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-overview-empty")).toBeTruthy();
  });
});

describe("IgVisaoGeral — success", () => {
  it("renders KPIs, trend empty state, and posts empty state", async () => {
    const { getByTestId, getByText } = await renderPage();
    expect(getByTestId("ig-overview-success")).toBeTruthy();
    expect(getByText("@minhaempresa")).toBeTruthy();
    expect(getByTestId("ig-trend-empty")).toBeTruthy();
    expect(getByTestId("ig-posts-empty")).toBeTruthy();
  });

  it("calls the capture mutation on 'Capturar agora'", async () => {
    const mutate = vi.fn();
    mockUseCaptureIgSnapshot.mockReturnValue({ mutate, isPending: false });
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("ig-capture-btn"));
    expect(mutate).toHaveBeenCalled();
  });

  it("passes the integration_accounts id — never the IG graph id — to every data hook", async () => {
    // Regression: the trend chart and posts table were handed
    // `context.instagram.id` (Meta's numeric graph id) instead of the
    // `integration_accounts` row id. The backend does `UUID(account_id)`
    // on that query param, so both calls 400'd with "invalid account_id"
    // in prod while the KPI tiles (fed by context) rendered fine.
    await renderPage();

    const graphId = makeAccount().id;
    for (const hook of [mockUseIgSnapshots, mockUseIgMedia, mockUseIgInsights]) {
      expect(hook).toHaveBeenCalled();
      for (const call of hook.mock.calls) {
        expect(call[0]).toBe("acc-1");
        expect(call[0]).not.toBe(graphId);
      }
    }
  });

  it("surfaces the insights error banner", async () => {
    mockUseIgInsights.mockReturnValue({
      data: { object_id: "x", metrics: {}, series: [], error: "permissão negada" },
      isPending: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-insights-error")).toBeTruthy();
  });
});
