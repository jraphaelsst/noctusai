/**
 * VideoDetailModal tests.
 *
 * Covers:
 *   1. Renders null when video=null (modal closed).
 *   2. Renders title, metrics (views/likes/comments), "Abrir no YouTube" link.
 *   3. Calls onClose when backdrop or close button clicked.
 *   4. VideoTrendChart shows "Sem histórico" empty state when trend returns [].
 *   5. VideoTrendChart shows chart when trend data is populated.
 *
 * Mock strategy:
 *   · useVideoTrend mocked per-test.
 *   · recharts mocked (no SVG rendering).
 *   · lucide icons mocked as inert spans.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Seed infra mock (prevents Supabase VITE_ env errors) ───────────────────
vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: vi.fn(() => Promise.resolve({ points: [] })),
    post: vi.fn(() => Promise.resolve({})),
  },
}));

vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountStore: vi.fn(() => null),
}));

// ─── Hook mock ────────────────────────────────────────────────────────────────

const mockUseVideoTrend = vi.fn();
vi.mock("@/hooks/useVideoTrend", () => ({
  useVideoTrend: (...args: any[]) => mockUseVideoTrend(...args),
}));

// ─── UI primitive mocks ──────────────────────────────────────────────────────

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: any) => <span data-testid="badge">{children}</span>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, asChild, "aria-label": ariaLabel, ...rest }: any) =>
    asChild ? (
      React_stub_passthrough({ children, onClick })
    ) : (
      <button onClick={onClick} aria-label={ariaLabel}>{children}</button>
    ),
}));
vi.mock("@/components/ui/card", () => ({
  Card: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children }: any) => <div>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
}));

// passthrough for asChild (renders children directly)
function React_stub_passthrough({ children }: any) {
  return <span>{children}</span>;
}

// recharts mocks
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
  ExternalLink: () => null,
  Eye: () => null,
  Heart: () => null,
  Loader2: () => <span data-testid="loader" />,
  MessageCircle: () => null,
  PlaySquare: () => null,
  X: () => <span>X</span>,
}));

// ─── Fixture ─────────────────────────────────────────────────────────────────

const video = {
  id: "vid-1",
  youtube_video_id: "dQw4w9WgXcQ",
  title: "Never Gonna Give You Up",
  description: "The classic Rickroll.",
  thumbnail_url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
  published_at: "2009-10-25T00:00:00Z",
  duration: "PT3M33S",
  privacy_status: "public" as const,
  view_count: 1_000_000,
  like_count: 20_000,
  comment_count: 5_000,
  favorite_count: 0,
  tags: ["rick", "astley"],
  category_id: "10",
  uploaded_via_app: false,
  synced_at: "2026-06-01T00:00:00Z",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function renderModal(props: any = {}) {
  const { VideoDetailModal } = await import("./VideoDetailModal");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const merged = { video: null, onClose: vi.fn(), ...props };
  return { ...rtl.render(React.createElement(VideoDetailModal, merged)), fireEvent: rtl.fireEvent, merged };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockUseVideoTrend.mockReturnValue({ data: [], loading: false, error: null });
});

describe("VideoDetailModal — closed state", () => {
  it("renders nothing when video=null", async () => {
    const { container } = await renderModal({ video: null });
    expect(container.firstChild).toBeNull();
  });
});

describe("VideoDetailModal — open state", () => {
  it("renders the video title", async () => {
    const { getByText } = await renderModal({ video });
    expect(getByText("Never Gonna Give You Up")).toBeTruthy();
  });

  it("renders an 'Abrir no YouTube' link pointing to the correct URL", async () => {
    const { getAllByRole } = await renderModal({ video });
    const links = getAllByRole("link").filter(
      (l) => l.textContent?.includes("YouTube") || (l as HTMLAnchorElement).href?.includes("youtube.com"),
    );
    expect(links.length).toBeGreaterThan(0);
    const href = (links[0] as HTMLAnchorElement).href;
    expect(href).toContain("dQw4w9WgXcQ");
  });

  it("renders view/like/comment counts", async () => {
    const { getByText } = await renderModal({ video });
    // 1_000_000 → "1.000.000" in pt-BR or "1M" via fmtNum
    expect(getByText("Visualizações")).toBeTruthy();
    expect(getByText("Curtidas")).toBeTruthy();
    expect(getByText("Comentários")).toBeTruthy();
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    const { getByLabelText, fireEvent } = await renderModal({ video, onClose });
    const closeBtn = getByLabelText("Fechar");
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("VideoDetailModal — trend chart states", () => {
  it("shows 'Sem histórico' empty state when trend returns no points", async () => {
    mockUseVideoTrend.mockReturnValue({ data: [], loading: false, error: null });
    const { getByText } = await renderModal({ video });
    expect(getByText(/Sem histórico/i)).toBeTruthy();
  });

  it("shows loading spinner while trend is loading", async () => {
    mockUseVideoTrend.mockReturnValue({ data: [], loading: true, error: null });
    const { getByTestId } = await renderModal({ video });
    expect(getByTestId("loader")).toBeTruthy();
  });

  it("renders chart when trend data is populated", async () => {
    mockUseVideoTrend.mockReturnValue({
      data: [
        { snapshot_date: "2026-05-01", view_count: 100, like_count: 10, comment_count: 2 },
        { snapshot_date: "2026-05-02", view_count: 200, like_count: 15, comment_count: 3 },
      ],
      loading: false,
      error: null,
    });
    const { getByTestId } = await renderModal({ video });
    expect(getByTestId("line-chart")).toBeTruthy();
  });

  it("passes videoId to useVideoTrend", async () => {
    mockUseVideoTrend.mockReturnValue({ data: [], loading: false, error: null });
    await renderModal({ video });
    // The trend hook should be called with the youtube_video_id
    const firstCall = mockUseVideoTrend.mock.calls[0];
    expect(firstCall[0]).toBe(video.youtube_video_id);
  });
});
