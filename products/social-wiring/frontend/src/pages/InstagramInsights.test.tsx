/**
 * InstagramInsights.test.tsx — unit tests for the Instagram insights page.
 *
 * Covers:
 *   1. Status loading → skeleton.
 *   2. adapter=="fake" → "Conectar Instagram" CTA; click navigates to
 *      /api/meta/oauth/start.
 *   3. consent_required==true → same CTA.
 *   4. Connected + accounts loading → skeleton.
 *   5. Connected + accounts error → error card.
 *   6. Connected + zero accounts → empty card.
 *   7. Connected + one account → KPI cards render, no account picker.
 *   8. Connected + >1 accounts → account picker renders.
 *   9. "Capturar agora" click calls the capture mutation.
 *
 * Mocks every hook + UI primitive (mirrors EmailMarketingConfig.test.tsx /
 * VideoDetailModal.test.tsx conventions) — no real TanStack Query provider
 * needed, avoiding the seed/lib vitest render-harness dual-React gap.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseMetaStatus = vi.fn();
const mockUseIgAccounts = vi.fn();
const mockUseIgInsights = vi.fn();
const mockUseIgMedia = vi.fn();
const mockUseIgSnapshots = vi.fn();
const mockUseCaptureIgSnapshot = vi.fn();

vi.mock("@/hooks/useInstagramInsights", () => ({
  useMetaStatus: mockUseMetaStatus,
  useIgAccounts: mockUseIgAccounts,
  useIgInsights: mockUseIgInsights,
  useIgMedia: mockUseIgMedia,
  useIgSnapshots: mockUseIgSnapshots,
  useCaptureIgSnapshot: mockUseCaptureIgSnapshot,
}));

vi.mock("@/lib/apiBase", () => ({
  apiUrl: (path: string) => `http://localhost:8011${path}`,
}));

// ─── UI stubs ────────────────────────────────────────────────────────────────

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...props }: any) => <div {...props}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt} {...rest}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ "data-testid": dt }: any) => <div data-testid={dt ?? "skeleton"} />,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children, "data-testid": dt }: any) => (
    <div data-testid={dt}>{children}</div>
  ),
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children, value }: any) => <div data-value={value}>{children}</div>,
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
  Camera: () => <span data-testid="icon-camera" />,
  CircleAlert: () => <span data-testid="icon-alert" />,
  Eye: () => null,
  Grid3x3: () => null,
  Instagram: () => <span data-testid="icon-instagram" />,
  Loader2: () => <span data-testid="icon-loader" />,
  RefreshCw: () => null,
  Users: () => null,
  UserPlus: () => null,
}));

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeAccount = (overrides: Partial<any> = {}) => ({
  id: "17841400000000000",
  username: "minhaempresa",
  name: "Minha Empresa",
  followers_count: 1200,
  follows_count: 300,
  media_count: 42,
  ...overrides,
});

function setDefaults() {
  mockUseMetaStatus.mockReturnValue({
    data: { adapter: "oauth", consent_required: false, error: null },
    isLoading: false,
  });
  mockUseIgAccounts.mockReturnValue({
    data: { accounts: [makeAccount()], adapter: "oauth" },
    isLoading: false,
    isError: false,
  });
  mockUseIgInsights.mockReturnValue({
    data: { object_id: "x", metrics: { reach: 500, profile_views: 80 }, series: [] },
    isLoading: false,
  });
  mockUseIgMedia.mockReturnValue({
    data: { media: [] },
    isLoading: false,
    isError: false,
  });
  mockUseIgSnapshots.mockReturnValue({
    data: { snapshots: [] },
    isLoading: false,
    isError: false,
  });
  mockUseCaptureIgSnapshot.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  });
}

beforeEach(() => {
  setDefaults();
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderPage() {
  const React = (await import("react")).default;
  const { default: InstagramInsights } = await import("./InstagramInsights");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(InstagramInsights)), fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("InstagramInsights — status loading", () => {
  it("renders a skeleton while status is loading", async () => {
    mockUseMetaStatus.mockReturnValue({ data: undefined, isLoading: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-status-loading")).toBeTruthy();
  });
});

describe("InstagramInsights — needs connect", () => {
  it("renders the Conectar Instagram CTA when adapter=='fake'", async () => {
    mockUseMetaStatus.mockReturnValue({
      data: { adapter: "fake", consent_required: false, error: null },
      isLoading: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-connect-card")).toBeTruthy();
    expect(getByTestId("ig-connect-btn")).toBeTruthy();
  });

  it("renders the CTA when consent_required==true even if adapter isn't fake", async () => {
    mockUseMetaStatus.mockReturnValue({
      data: { adapter: "oauth", consent_required: true, error: null },
      isLoading: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-connect-card")).toBeTruthy();
  });

  it("clicking the connect button navigates to /api/meta/oauth/start", async () => {
    mockUseMetaStatus.mockReturnValue({
      data: { adapter: "fake", consent_required: false, error: null },
      isLoading: false,
    });
    const assignSpy = vi.fn();
    // @ts-expect-error jsdom location is not fully typed for reassignment
    delete (window as any).location;
    (window as any).location = { assign: assignSpy };

    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("ig-connect-btn"));
    expect(assignSpy).toHaveBeenCalledWith(
      "http://localhost:8011/api/meta/oauth/start",
    );
  });

  it("surfaces the status error message on the CTA card", async () => {
    mockUseMetaStatus.mockReturnValue({
      data: { adapter: "fake", consent_required: false, error: "token expirado" },
      isLoading: false,
    });
    const { getByText } = await renderPage();
    expect(getByText("token expirado")).toBeTruthy();
  });
});

describe("InstagramInsights — accounts states", () => {
  it("renders a skeleton while accounts are loading", async () => {
    mockUseIgAccounts.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-accounts-loading")).toBeTruthy();
  });

  it("renders an error card when accounts fail to load", async () => {
    mockUseIgAccounts.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-accounts-error")).toBeTruthy();
  });

  it("renders an empty card when there are zero accounts", async () => {
    mockUseIgAccounts.mockReturnValue({
      data: { accounts: [], adapter: "oauth" },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-accounts-empty")).toBeTruthy();
  });
});

describe("InstagramInsights — single account success", () => {
  it("renders KPI cards and no account picker", async () => {
    const { getByText, queryByTestId } = await renderPage();
    expect(getByText("@minhaempresa")).toBeTruthy();
    expect(getByText("1.2K")).toBeTruthy(); // followers_count formatted
    expect(queryByTestId("ig-account-select")).toBeNull();
  });

  it("renders the followers trend empty state when there are no snapshots", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-trend-empty")).toBeTruthy();
  });

  it("renders the posts empty state when there is no media", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-posts-empty")).toBeTruthy();
  });

  it("renders the per-post insights error banner when insights.error is set", async () => {
    mockUseIgInsights.mockReturnValue({
      data: { object_id: "x", metrics: {}, series: [], error: "permissão negada" },
      isLoading: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-insights-error")).toBeTruthy();
  });
});

describe("InstagramInsights — multi-account picker", () => {
  it("renders the account picker when there is more than one account", async () => {
    mockUseIgAccounts.mockReturnValue({
      data: {
        accounts: [makeAccount(), makeAccount({ id: "2", username: "outraempresa" })],
        adapter: "oauth",
      },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("ig-account-select")).toBeTruthy();
  });
});

describe("InstagramInsights — capture snapshot", () => {
  it("calls the capture mutation when 'Capturar agora' is clicked", async () => {
    const mutate = vi.fn();
    mockUseCaptureIgSnapshot.mockReturnValue({ mutate, isPending: false });
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("ig-capture-btn"));
    expect(mutate).toHaveBeenCalled();
  });
});
