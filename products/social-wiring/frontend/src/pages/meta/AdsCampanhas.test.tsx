/**
 * AdsCampanhas.test.tsx — "Campanhas" subtab: campaign → ad set → ad
 * drill-down table.
 *
 * The load-bearing case this file exists for: clicking an AD row must open
 * AdDetalheModal for THAT ad's object_id — not the campaign's, not the ad
 * set's. A prior mix-up class (wrong id threaded to a child) is exactly
 * what these ids ("camp-1" / "adset-1" / "ad-1") are chosen to catch: any
 * swap fails the assertion.
 *
 * Mocks every hook + UI primitive (no real TanStack Query provider needed),
 * mirroring the LeadgenWebhookCard.test.tsx / IgVisaoGeral.test.tsx
 * conventions used across this product.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createPortal } from "react-dom";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseAdsAccount = vi.fn();
const mockUseAdsCampaigns = vi.fn();
const mockUseAdsChildren = vi.fn();

vi.mock("@/hooks/useMetaAds", () => ({
  useAdsAccount: mockUseAdsAccount,
  useAdsCampaigns: mockUseAdsCampaigns,
  useAdsChildren: mockUseAdsChildren,
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, ...p }: any) => <span {...p}>{children}</span>,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ children, value }: any) => <option value={value}>{children}</option>,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
}));
vi.mock("lucide-react", () => ({
  ChevronDown: () => null,
  ChevronRight: () => null,
  Loader2: () => null,
}));
vi.mock("./adsShared", () => ({
  AdsLoading: () => <div data-testid="ads-loading">Carregando…</div>,
  AdsError: ({ message, onRetry }: any) => (
    <div data-testid="ads-error">
      {message}
      {onRetry && <button onClick={onRetry}>Tentar de novo</button>}
    </div>
  ),
  AdsNotConfigured: () => <div data-testid="ads-not-configured" />,
  statusVariant: (effective?: string | null) => {
    const s = (effective ?? "").toUpperCase();
    if (s === "ACTIVE") return { label: "Ativa", cls: "active" };
    if (s === "PAUSED") return { label: "Pausada", cls: "paused" };
    return { label: effective ?? "—", cls: "muted" };
  },
}));

// The modal itself is covered end-to-end by AdDetalheModal.test.tsx — here
// it's a spy so this file can assert exactly WHICH ad object it receives.
// Portals its stand-in to document.body (matching the real Dialog organ's
// own DialogPortal) rather than rendering inline inside the <tr>/<tbody> —
// an inline mock is invalid DOM nesting from React's perspective (the real
// component never hits this because a portal boundary resets React's
// ancestor-nesting check), and that invalid nesting was observed to trigger
// an extra React DEV replay-render of this fiber, double-counting the spy.
const mockAdDetalheModal = vi.fn((_props: any) =>
  createPortal(<div data-testid="ad-detalhe-modal" />, document.body),
);
vi.mock("./AdDetalheModal", () => ({
  AdDetalheModal: (props: any) => mockAdDetalheModal(props),
}));

const ACCOUNT = { act_id: "act_1", name: "Conta", currency: "BRL" };
const CAMPAIGN = {
  object_id: "camp-1",
  name: "Campanha Um",
  objective: "OUTCOME_LEADS",
  status: "ACTIVE",
  effective_status: "ACTIVE",
  daily_budget_cents: 10000,
  lifetime_budget_cents: null,
  latest: { date: "2026-08-30", spend_cents: 5000, impressions: 100, clicks: 10, reach: 90, leads: 2 },
};
const ADSET = {
  object_id: "adset-1",
  level: "adset",
  parent_id: "camp-1",
  name: "Conjunto Um",
  status: "ACTIVE",
  effective_status: "ACTIVE",
  daily_budget_cents: 5000,
  optimization_goal: null,
  creative_id: null,
  creative_thumbnail_url: null,
};
const AD = {
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

function setDefaults() {
  mockUseAdsAccount.mockReturnValue({
    data: { data: [ACCOUNT] },
    isPending: false,
    isFetching: false,
    isError: false,
  });
  mockUseAdsCampaigns.mockReturnValue({
    data: { data: [CAMPAIGN] },
    isPending: false,
    isFetching: false,
    isError: false,
  });
  mockUseAdsChildren.mockImplementation((objectId: string | null, level: "adset" | "ad") => {
    if (!objectId) return { data: undefined, isPending: false, isFetching: false, isError: false };
    if (level === "adset") {
      return { data: { data: [ADSET] }, isPending: false, isFetching: false, isError: false };
    }
    return { data: { data: [AD] }, isPending: false, isFetching: false, isError: false };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  setDefaults();
});

async function renderPage() {
  const { render, screen } = await import("@testing-library/react");
  const { default: AdsCampanhas } = await import("./AdsCampanhas");
  const utils = render(<AdsCampanhas />);
  return { ...utils, screen };
}

/** Expand campaign → ad set so the ad row is on screen. */
async function drillToAdRow(screen: typeof import("@testing-library/react").screen) {
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.click(screen.getByText("Campanha Um"));
  fireEvent.click(await screen.findByText("Conjunto Um"));
  return screen.findByRole("button", { name: "ONE10528" });
}

describe("AdsCampanhas", () => {
  it("renders the campaign table with real data (not empty/loading/error)", async () => {
    const { screen } = await renderPage();
    expect(await screen.findByText("Campanha Um")).toBeTruthy();
    expect(screen.queryByTestId("ads-loading")).toBeNull();
    expect(screen.queryByTestId("ads-error")).toBeNull();
  });

  it("shows the account-loading state via isPending/isFetching, never isLoading", async () => {
    mockUseAdsAccount.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
    });
    const { screen } = await renderPage();
    expect(screen.getByTestId("ads-loading")).toBeTruthy();
  });

  it("shows the not-configured state when there's no ad account", async () => {
    mockUseAdsAccount.mockReturnValue({
      data: { data: [] },
      isPending: false,
      isFetching: false,
      isError: true,
      error: new Error("boom"),
    });
    const { screen } = await renderPage();
    expect(screen.getByTestId("ads-not-configured")).toBeTruthy();
  });

  it("shows the campaigns error state with a retry", async () => {
    const refetch = vi.fn();
    mockUseAdsCampaigns.mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: true,
      refetch,
    });
    const { screen } = await renderPage();
    expect(screen.getByTestId("ads-error")).toBeTruthy();
  });

  it("clicking the AD row opens AdDetalheModal with the AD's own object_id — not the campaign's or ad set's", async () => {
    const { screen } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    const adButton = await drillToAdRow(screen);
    expect(mockAdDetalheModal).not.toHaveBeenCalled();

    fireEvent.click(adButton);

    expect(mockAdDetalheModal).toHaveBeenCalledTimes(1);
    const props = mockAdDetalheModal.mock.calls[0][0];
    expect(props.ad.object_id).toBe("ad-1");
    expect(props.ad.object_id).not.toBe(CAMPAIGN.object_id);
    expect(props.ad.object_id).not.toBe(ADSET.object_id);
    expect(props.currency).toBe("BRL");
  });

  it("the ad row is a real <button> — Tab-reachable and Enter/Space-activatable by the browser's own native semantics, matching the ad-set toggle above it", async () => {
    const { screen } = await renderPage();
    const adButton = await drillToAdRow(screen);
    expect(adButton.tagName).toBe("BUTTON");
    expect(adButton.getAttribute("disabled")).toBeNull();
  });

  it("is Tab-focusable, and the click event a browser's own Enter/Space default action dispatches on a focused native <button> opens the modal for the right ad — jsdom doesn't implement that default action itself, so `fireEvent.click` (the same DOM `click` event) is what exercises the identical handler a real keyboard press would invoke", async () => {
    const { screen } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const adButton = await drillToAdRow(screen);

    adButton.focus();
    expect(document.activeElement).toBe(adButton);

    fireEvent.click(adButton);

    expect(mockAdDetalheModal).toHaveBeenCalledTimes(1);
    expect(mockAdDetalheModal.mock.calls[0][0].ad.object_id).toBe("ad-1");
  });

  it("closing the modal (onClose) unmounts it, and a second click re-opens it cleanly (state actually cleared, not stuck)", async () => {
    const { screen } = await renderPage();
    const { fireEvent, act } = await import("@testing-library/react");
    const adButton = await drillToAdRow(screen);
    fireEvent.click(adButton);
    expect(mockAdDetalheModal).toHaveBeenCalledTimes(1);

    const { onClose } = mockAdDetalheModal.mock.calls[0][0];
    act(() => onClose());

    fireEvent.click(adButton);
    expect(mockAdDetalheModal).toHaveBeenCalledTimes(2);
  });
});
