/**
 * FbVisaoGeral.test.tsx — Facebook "Visão geral" subtab (page insights).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseActiveMetaAccountId = vi.fn();
const mockUseMetaContext = vi.fn();
const mockUseFbInsights = vi.fn();

vi.mock("@/hooks/useMeta", () => ({
  useActiveMetaAccountId: mockUseActiveMetaAccountId,
  useMetaContext: mockUseMetaContext,
  useFbInsights: mockUseFbInsights,
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ "data-testid": dt }: any) => <div data-testid={dt ?? "skeleton"} />,
}));
vi.mock("@/components/MetricCard", () => ({
  MetricCard: ({ label, value }: any) => <div>{label}: {value}</div>,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children, value, onValueChange }: any) => (
    <select value={value} onChange={(e) => onValueChange(e.target.value)} data-testid="select">
      {children}
    </select>
  ),
  SelectTrigger: ({ children, "data-testid": dt }: any) => <div data-testid={dt}>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ children, value }: any) => <option value={value}>{children}</option>,
}));
vi.mock("lucide-react", () => ({
  BarChart3: () => null,
  CircleAlert: () => <span data-testid="icon-alert" />,
}));

function setDefaults() {
  mockUseActiveMetaAccountId.mockReturnValue("acc-1");
  mockUseMetaContext.mockReturnValue({
    data: { instagram: null, pages: [{ id: "page-1", name: "Minha Página" }], user: null },
    isPending: false,
    isError: false,
  });
  mockUseFbInsights.mockReturnValue({ data: { object_id: "page-1", metrics: {}, series: [] }, isPending: false, isError: false });
}

beforeEach(() => setDefaults());

async function renderPage() {
  const React = (await import("react")).default;
  const { default: FbVisaoGeral } = await import("./FbVisaoGeral");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(FbVisaoGeral)), fireEvent: rtl.fireEvent };
}

describe("FbVisaoGeral — no account selected", () => {
  it("shows the select-an-account prompt", async () => {
    mockUseActiveMetaAccountId.mockReturnValue(null);
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-overview-no-account")).toBeTruthy();
  });
});

describe("FbVisaoGeral — context states", () => {
  it("renders a loading state", async () => {
    mockUseMetaContext.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-context-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseMetaContext.mockReturnValue({ data: undefined, isPending: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-context-error")).toBeTruthy();
  });

  it("renders a no-pages state", async () => {
    mockUseMetaContext.mockReturnValue({
      data: { instagram: null, pages: [], user: null },
      isPending: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-no-pages")).toBeTruthy();
  });
});

describe("FbVisaoGeral — insights states", () => {
  it("renders a loading state", async () => {
    mockUseFbInsights.mockReturnValue({ data: undefined, isPending: true, isError: false });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-insights-loading")).toBeTruthy();
  });

  it("renders an error state", async () => {
    mockUseFbInsights.mockReturnValue({ data: undefined, isPending: false, isError: true });
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-insights-error")).toBeTruthy();
  });

  it("renders an empty state when there are no metrics", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("fb-insights-empty")).toBeTruthy();
  });

  it("renders metric cards on success", async () => {
    mockUseFbInsights.mockReturnValue({
      data: { object_id: "page-1", metrics: { page_impressions: 500 }, series: [] },
      isPending: false,
      isError: false,
    });
    const { getByTestId, getByText } = await renderPage();
    expect(getByTestId("fb-insights-success")).toBeTruthy();
    expect(getByText(/page impressions/)).toBeTruthy();
  });
});
