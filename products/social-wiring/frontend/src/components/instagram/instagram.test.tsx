/**
 * Shared Instagram insights components: post card, insights modal (seed
 * MediaInsightsModal), profile view, post grid. Hooks are mocked; the seed
 * organs render for real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

afterEach(cleanup);

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const h = vi.hoisted(() => ({
  profile: vi.fn(),
  trend: vi.fn(),
  media: vi.fn(),
  history: vi.fn(),
  sync: vi.fn(),
  oauth: vi.fn(),
}));

vi.mock("@/hooks/useInstagramInsights", async (orig) => ({
  ...(await orig<typeof import("@/hooks/useInstagramInsights")>()),
  useInstagramProfile: h.profile,
  useInstagramTrend: h.trend,
  useInstagramMedia: h.media,
  useInstagramMediaHistory: h.history,
  useInstagramSync: h.sync,
}));
vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useStartProviderOAuth: h.oauth,
}));

import { InstagramPostCard } from "./InstagramPostCard";
import { InstagramPostInsightsModal } from "./InstagramPostInsightsModal";
import { InstagramPostGrid } from "./InstagramPostGrid";
import { InstagramProfileView } from "./InstagramProfileView";

const item = (over: Record<string, unknown> = {}) => ({
  id: "m1",
  media_type: "VIDEO",
  media_product_type: "REELS",
  caption: "Legenda do reel",
  permalink: "https://www.instagram.com/reel/abc/",
  thumbnail_url: "https://x/t.jpg",
  media_url: null,
  timestamp: "2026-10-05T12:00:00+00:00",
  like_count: 42,
  comments_count: 3,
  latest: { views: 500, reach: 300, saved: null, shares: 7 },
  latest_snapshot_date: "2026-10-06",
  synced_at: "2026-10-06T08:30:00+00:00",
  ...over,
});

const query = (over: Record<string, unknown> = {}) => ({
  data: undefined,
  isPending: false,
  isFetching: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

const profile = (over: Record<string, unknown> = {}) => ({
  account_id: "a1",
  marca_id: "mc1",
  ig_user_id: "1",
  username: "acme",
  name: "Acme",
  profile_picture_url: null,
  followers_count: 1500,
  follows_count: 12,
  media_count: 230,
  biography: null,
  website: null,
  last_synced_at: "2026-10-06T08:30:00+00:00",
  insights_scope_granted: true,
  ...over,
});

const trendPoints = [
  { date: "2026-10-04", followers_count: 1480, views: 100, total_interactions: 10, comments: 1, reach: 50 },
  { date: "2026-10-05", followers_count: 1490, views: 200, total_interactions: 20, comments: 2, reach: 60 },
  { date: "2026-10-06", followers_count: 1500, views: 300, total_interactions: 30, comments: 3, reach: 70 },
];

const syncMutation = (over: Record<string, unknown> = {}) => ({
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  data: undefined,
  ...over,
});

beforeEach(() => {
  h.profile.mockReturnValue(query({ data: profile() }));
  h.trend.mockReturnValue(query({ data: { points: trendPoints, metrics: [] } }));
  h.sync.mockReturnValue(syncMutation());
  h.oauth.mockReturnValue({ mutate: vi.fn(), isPending: false });
  h.media.mockReturnValue({
    ...query({ data: { pages: [{ items: [item()], next_cursor: null }] } }),
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  });
  h.history.mockReturnValue(query());
});

describe("InstagramPostCard", () => {
  it("shows kind, date and the six metrics; null renders '—' (not 0)", () => {
    const onOpen = vi.fn();
    render(<InstagramPostCard item={item() as never} onOpen={onOpen} />);
    expect(screen.getByText("Reel")).toBeTruthy();
    expect(screen.getByText("05/10/2026")).toBeTruthy();
    expect(screen.getByTestId("ig-post-stat-Curtidas").textContent).toBe("42");
    expect(screen.getByTestId("ig-post-stat-Compartilhamentos").textContent).toBe("7");
    expect(screen.getByTestId("ig-post-stat-Salvamentos").textContent).toBe("—");
    fireEvent.click(screen.getByTestId("ig-post-card"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("hidden like count is '—', not 0", () => {
    render(<InstagramPostCard item={item({ like_count: null, latest: null }) as never} onOpen={vi.fn()} />);
    expect(screen.getByTestId("ig-post-stat-Curtidas").textContent).toBe("—");
    expect(screen.getByTestId("ig-post-stat-Alcance").textContent).toBe("—");
  });
});

describe("InstagramPostInsightsModal", () => {
  const history = {
    media: item(),
    // metrics deliberately out of priority order
    metrics: [
      { key: "reach", label: "Contas alcançadas", format: "int", priority: 2 },
      { key: "views", label: "Visualizações", format: "int", priority: 1 },
      { key: "saved", label: "Salvamentos", format: "int", priority: 8 },
    ],
    points: [
      { date: "2026-10-05", views: 480, reach: 290, saved: null },
      { date: "2026-10-06", views: 500, reach: 300, saved: null },
    ],
  };

  it("renders nothing without a media", () => {
    const { container } = render(<InstagramPostInsightsModal accountId="a1" media={null} onClose={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  it("opens with metrics sorted by priority, null KPI as '—', and an Instagram link", () => {
    h.history.mockReturnValue(query({ data: history }));
    render(<InstagramPostInsightsModal accountId="a1" media={item() as never} onClose={vi.fn()} />);
    const modal = screen.getByTestId("media-insights-modal");
    const text = modal.textContent ?? "";
    expect(text.indexOf("Visualizações")).toBeGreaterThan(-1);
    expect(text.indexOf("Visualizações")).toBeLessThan(text.indexOf("Contas alcançadas"));
    expect(text.indexOf("Contas alcançadas")).toBeLessThan(text.indexOf("Salvamentos"));
    expect(within(modal).getByText("—")).toBeTruthy();
    const link = within(modal).getByText(/Abrir no Instagram/).closest("a");
    expect(link?.getAttribute("href")).toBe("https://www.instagram.com/reel/abc/");
    expect(link?.getAttribute("target")).toBe("_blank");
  });

  it("skeleton only without data; a refetch over data keeps content (no skeleton)", () => {
    h.history.mockReturnValue(query({ isPending: true, isFetching: true }));
    const { unmount } = render(<InstagramPostInsightsModal accountId="a1" media={item() as never} onClose={vi.fn()} />);
    expect(screen.queryByText("Contas alcançadas")).toBeNull();
    unmount();
    h.history.mockReturnValue(query({ data: history, isFetching: true }));
    render(<InstagramPostInsightsModal accountId="a1" media={item() as never} onClose={vi.fn()} />);
    expect(screen.getAllByText("Contas alcançadas").length).toBeGreaterThan(0);
  });

  it("shows the error state with retry when there is no data", () => {
    h.history.mockReturnValue(query({ isError: true }));
    render(<InstagramPostInsightsModal accountId="a1" media={item() as never} onClose={vi.fn()} />);
    expect(screen.getByText(/Erro ao carregar o histórico/)).toBeTruthy();
  });
});

describe("InstagramPostGrid", () => {
  it("keeps the server order, loads more, and opens the modal (not a link)", () => {
    const fetchNextPage = vi.fn();
    h.media.mockReturnValue({
      ...query({
        data: {
          pages: [
            { items: [item({ id: "new", timestamp: "2026-10-05T12:00:00+00:00" })], next_cursor: "c" },
            { items: [item({ id: "old", timestamp: "2026-09-01T12:00:00+00:00" })], next_cursor: null },
          ],
        },
      }),
      hasNextPage: true,
      isFetchingNextPage: false,
      fetchNextPage,
    });
    render(<InstagramPostGrid accountId="a1" />);
    const dates = screen.getAllByTestId("ig-post-card").map((c) => c.textContent ?? "");
    expect(dates[0]).toContain("05/10/2026");
    expect(dates[1]).toContain("01/09/2026");
    fireEvent.click(screen.getByTestId("ig-grid-load-more"));
    expect(fetchNextPage).toHaveBeenCalled();
    fireEvent.click(screen.getAllByTestId("ig-post-card")[0]);
    expect(screen.getByTestId("media-insights-modal")).toBeTruthy();
    expect(h.history).toHaveBeenLastCalledWith("a1", "new");
  });

  it("skeleton / empty / error / refreshing signals", () => {
    h.media.mockReturnValue({ ...query({ isPending: true, isFetching: true }), hasNextPage: false });
    const a = render(<InstagramPostGrid accountId="a1" />);
    expect(screen.getByTestId("ig-grid-loading")).toBeTruthy();
    a.unmount();

    h.media.mockReturnValue({ ...query({ data: { pages: [{ items: [], next_cursor: null }] } }), hasNextPage: false });
    const b = render(<InstagramPostGrid accountId="a1" />);
    expect(screen.getByTestId("ig-grid-empty").textContent).toMatch(/coletados diariamente/);
    b.unmount();

    h.media.mockReturnValue({ ...query({ isError: true }), hasNextPage: false });
    const c = render(<InstagramPostGrid accountId="a1" />);
    expect(screen.getByTestId("ig-grid-error")).toBeTruthy();
    c.unmount();

    h.media.mockReturnValue({
      ...query({ data: { pages: [{ items: [item()], next_cursor: null }] }, isFetching: true }),
      hasNextPage: false,
      isFetchingNextPage: false,
    });
    render(<InstagramPostGrid accountId="a1" />);
    expect(screen.getByTestId("ig-grid")).toBeTruthy();
    expect(screen.getByTestId("ig-grid-refreshing")).toBeTruthy();
    expect(screen.queryByTestId("ig-grid-loading")).toBeNull();
  });
});

describe("InstagramProfileView", () => {
  it("renders header, derived KPIs and both chart cards", () => {
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.getByTestId("ig-username").textContent).toBe("@acme");
    for (const l of ["Seguidores", "Novos seguidores", "Visualizações", "Engajamento", "Comentários", "Alcance"]) {
      expect(screen.getAllByText(l).length).toBeGreaterThan(0);
    }
    // 30d: followers 1500-1480 = 20; views 100+200+300 = 600
    expect(screen.getByText("20")).toBeTruthy();
    expect(screen.getByText("600")).toBeTruthy();
    expect(screen.queryByTestId("ig-grid")).toBeNull();
  });

  it("'Último dia' uses the latest daily point and says so", () => {
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    fireEvent.click(screen.getByTestId("ig-period-last"));
    expect(screen.getByTestId("ig-chart-total_interactions-last").textContent).toContain("30");
    expect(screen.getByTestId("ig-chart-reach-last").textContent).toContain("último dia coletado");
    // growth vs previous capture: 1500 - 1490
    expect(screen.getByText("10")).toBeTruthy();
  });

  it("Novos seguidores is '—' when not derivable", () => {
    h.trend.mockReturnValue(query({ data: { points: [trendPoints[2]], metrics: [] } }));
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows the reconnect banner when the insights scope is missing and starts OAuth", () => {
    const mutate = vi.fn();
    h.oauth.mockReturnValue({ mutate, isPending: false });
    h.profile.mockReturnValue(query({ data: profile({ insights_scope_granted: false }) }));
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    fireEvent.click(screen.getByTestId("ig-reconnect-button"));
    expect(mutate).toHaveBeenCalledWith({ marcaId: "mc1" });
  });

  it("sync: button triggers mutate; 409 gate shows Reconectar; app review explains", () => {
    const mutate = vi.fn();
    h.sync.mockReturnValue(syncMutation({ mutate }));
    const a = render(<InstagramProfileView accountId="a1" showPosts={false} />);
    fireEvent.click(screen.getByTestId("ig-sync-button"));
    expect(mutate).toHaveBeenCalled();
    a.unmount();

    h.sync.mockReturnValue(syncMutation({ data: { requires_reconnect: true, error: "Reconecte" } }));
    const b = render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.getByTestId("ig-reconnect-banner").textContent).toContain("Reconecte");
    b.unmount();

    h.sync.mockReturnValue(syncMutation({ data: { requires_app_review: true, error: null } }));
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.getByTestId("ig-app-review-notice").textContent).toMatch(/Meta/);
  });

  it("empty state before first sync explains daily collection", () => {
    h.profile.mockReturnValue(query({ data: profile({ last_synced_at: null, followers_count: null }) }));
    h.trend.mockReturnValue(query({ data: { points: [], metrics: [] } }));
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.getByTestId("ig-no-data").textContent).toMatch(/todos os dias/);
  });

  it("skeleton only without data; refetch over data keeps the content", () => {
    h.profile.mockReturnValue(query({ isPending: true, isFetching: true }));
    h.trend.mockReturnValue(query({ isPending: true, isFetching: true }));
    const a = render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.queryByTestId("ig-username")).toBeNull();
    a.unmount();
    h.profile.mockReturnValue(query({ data: profile(), isFetching: true }));
    h.trend.mockReturnValue(query({ data: { points: trendPoints, metrics: [] }, isFetching: true }));
    render(<InstagramProfileView accountId="a1" showPosts={false} />);
    expect(screen.getByTestId("ig-username").textContent).toBe("@acme");
    expect(screen.getByText(/Atualizando…/)).toBeTruthy();
  });
});
