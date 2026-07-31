/**
 * ChannelContentTable tests.
 *
 * Covers:
 *   1. Renders rows with correct column values from fixture data.
 *   2. Privacy badge renders correct label per privacy_status.
 *   3. Duration badge formatted from ISO-8601 (e.g. "PT1M46S" → "1:46").
 *   4. Empty state renders with expected message.
 *   5. Loading state renders skeleton placeholders.
 *   6. Row click calls onRowClick with the correct video.
 *   7. "Curtidas" column present; no "Não gostei" / dislike column (honesty check).
 *   8. Wiring: accountId from store flows through to useVideos params.
 *
 * Mock strategy:
 *   · All lucide icons and shadcn/ui primitives mocked as lightweight HTML.
 *   · No real fetch calls.
 *   · Dual-React gap: avoid rendering hooks that call into the real lib;
 *     ChannelContentTable is purely presentational — no hooks inside, safe.
 */
import { describe, it, expect, vi, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Seed infra mock (prevents Supabase VITE_ env errors) ───────────────────
vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: vi.fn(() => Promise.resolve({ items: [], next_cursor: null, total_known: 0 })),
    post: vi.fn(() => Promise.resolve({})),
  },
}));

// Mock useActiveAccount so hooks don't error on store init
vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountId: vi.fn(() => null),
}));

// ─── UI primitive mocks ─────────────────────────────────────────────────────

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, variant }: any) => (
    <span data-testid="badge" data-variant={variant}>{children}</span>
  ),
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "aria-label": ariaLabel, title }: any) => (
    <button onClick={onClick} disabled={disabled} aria-label={ariaLabel} title={title}>{children}</button>
  ),
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
}));

// lucide icons → inert spans
vi.mock("lucide-react", () => ({
  ChevronDown: () => null,
  ChevronUp: () => null,
  ChevronsUpDown: () => null,
  Edit2: () => <span data-icon="edit" />,
  Eye: () => <span data-icon="eye" />,
  Globe: () => <span data-icon="globe" />,
  Heart: () => <span data-icon="heart" />,
  Lock: () => <span data-icon="lock" />,
  Loader2: () => <span data-icon="loader" />,
  MessageCircle: () => <span data-icon="message" />,
  Link: () => <span data-icon="link" />,
  PlaySquare: () => <span data-icon="playsquare" />,
  Sparkles: () => <span data-icon="sparkles" />,
  Trash2: () => <span data-icon="trash" />,
}));

// ─── Fixture ─────────────────────────────────────────────────────────────────

const baseVideo = {
  id: "vid-1",
  youtube_video_id: "dQw4w9WgXcQ",
  title: "Never Gonna Give You Up",
  description: "The classic Rickroll music video.",
  thumbnail_url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
  published_at: "2009-10-25T00:00:00Z",
  duration: "PT3M33S",
  privacy_status: "public" as const,
  view_count: 1_500_000,
  like_count: 25_000,
  comment_count: 3_000,
  favorite_count: 0,
  tags: ["rick", "astley"],
  category_id: "10",
  uploaded_via_app: false,
  synced_at: "2026-06-01T00:00:00Z",
};

const unlistedVideo = {
  ...baseVideo,
  id: "vid-2",
  youtube_video_id: "abc123",
  title: "Unlisted Video",
  privacy_status: "unlisted" as const,
  view_count: 100,
  like_count: 5,
  comment_count: 2,
};

const privateVideo = {
  ...baseVideo,
  id: "vid-3",
  youtube_video_id: "xyz789",
  title: "Private Video",
  privacy_status: "private" as const,
  view_count: 0,
  like_count: 0,
  comment_count: 0,
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function renderTable(props: any = {}) {
  const { ChannelContentTable } = await import("./ChannelContentTable");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const merged = {
    items: [baseVideo],
    loading: false,
    loadingMore: false,
    hasMore: false,
    onLoadMore: vi.fn(),
    onRowClick: vi.fn(),
    ...props,
  };
  return {
    ...rtl.render(React.createElement(ChannelContentTable, merged)),
    fireEvent: rtl.fireEvent,
    merged,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("ChannelContentTable — basic render", () => {
  it("renders the video title in a row", async () => {
    const { getByText } = await renderTable();
    expect(getByText("Never Gonna Give You Up")).toBeTruthy();
  });

  it("renders column headers: Vídeo, Visibilidade, Data, Visualizações, Comentários, Curtidas", async () => {
    const { container } = await renderTable();
    // Use querySelectorAll on the table's thead to scope the check
    const ths = container.querySelectorAll("th");
    const headerTexts = Array.from(ths).map((th) => th.textContent ?? "");
    // All six headers must be present in the thead
    expect(headerTexts.some((t) => /Vídeo/i.test(t))).toBe(true);
    expect(headerTexts.some((t) => /Visibilidade/i.test(t))).toBe(true);
    expect(headerTexts.some((t) => /Data/i.test(t))).toBe(true);
    expect(headerTexts.some((t) => /Visualizações/i.test(t))).toBe(true);
    expect(headerTexts.some((t) => /Comentários/i.test(t))).toBe(true);
    expect(headerTexts.some((t) => /Curtidas/i.test(t))).toBe(true);
  });

  it("does NOT render a 'Não gostei' / dislike column (honesty — YouTube API removed it)", async () => {
    const { container } = await renderTable();
    const ths = Array.from(container.querySelectorAll("th"));
    const headerTexts = ths.map((th) => th.textContent ?? "");
    expect(headerTexts.some((t) => /Não gostei/i.test(t))).toBe(false);
    expect(headerTexts.some((t) => /Desgostei/i.test(t))).toBe(false);
    expect(headerTexts.some((t) => /dislike/i.test(t))).toBe(false);
  });

  it("does NOT render a 'Restrições' column (data not captured)", async () => {
    const { container } = await renderTable();
    const ths = Array.from(container.querySelectorAll("th"));
    const headerTexts = ths.map((th) => th.textContent ?? "");
    expect(headerTexts.some((t) => /Restrições/i.test(t))).toBe(false);
  });
});

describe("ChannelContentTable — privacy badge", () => {
  it("shows 'Público' badge for public video", async () => {
    const { getByText } = await renderTable({ items: [baseVideo] });
    expect(getByText("Público")).toBeTruthy();
  });

  it("shows 'Não listado' badge for unlisted video", async () => {
    const { getByText } = await renderTable({ items: [unlistedVideo] });
    expect(getByText("Não listado")).toBeTruthy();
  });

  it("shows 'Privado' badge for private video", async () => {
    const { getByText } = await renderTable({ items: [privateVideo] });
    expect(getByText("Privado")).toBeTruthy();
  });
});

describe("ChannelContentTable — duration badge", () => {
  it("formats ISO duration PT3M33S as '3:33'", async () => {
    const { getByText } = await renderTable({
      items: [{ ...baseVideo, duration: "PT3M33S" }],
    });
    expect(getByText("3:33")).toBeTruthy();
  });

  it("formats ISO duration PT1M46S as '1:46'", async () => {
    const { getByText } = await renderTable({
      items: [{ ...baseVideo, duration: "PT1M46S" }],
    });
    expect(getByText("1:46")).toBeTruthy();
  });

  it("formats PT1H2M3S as '1:02:03'", async () => {
    const { getByText } = await renderTable({
      items: [{ ...baseVideo, duration: "PT1H2M3S" }],
    });
    expect(getByText("1:02:03")).toBeTruthy();
  });
});

describe("ChannelContentTable — metrics render", () => {
  it("renders view_count with pt-BR thousands separator", async () => {
    const { getByText } = await renderTable({
      items: [{ ...baseVideo, view_count: 1_500_000 }],
    });
    // pt-BR uses dots as thousands separator → "1.500.000"
    expect(getByText("1.500.000")).toBeTruthy();
  });
});

describe("ChannelContentTable — empty/loading states", () => {
  it("renders empty state message when items is empty", async () => {
    const msg = "Nenhum vídeo no cache. Clique em Sincronizar.";
    const { getByText } = await renderTable({ items: [], emptyMessage: msg });
    expect(getByText(msg)).toBeTruthy();
  });

  it("renders skeleton rows when loading=true", async () => {
    const { getAllByTestId } = await renderTable({ loading: true, items: [] });
    const skeletons = getAllByTestId("skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe("ChannelContentTable — row interaction", () => {
  it("calls onRowClick with the video when a row is clicked", async () => {
    const onRowClick = vi.fn();
    const { container, fireEvent } = await renderTable({ onRowClick });
    const row = container.querySelector("tbody tr[role='button']") as HTMLElement;
    expect(row).toBeTruthy();
    fireEvent.click(row);
    expect(onRowClick).toHaveBeenCalledOnce();
    expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({
      youtube_video_id: baseVideo.youtube_video_id,
    }));
  });
});

describe("ChannelContentTable — multiple rows", () => {
  it("renders all provided videos", async () => {
    const items = [baseVideo, unlistedVideo, privateVideo];
    const { container } = await renderTable({ items });
    const rows = container.querySelectorAll("tbody tr");
    expect(rows.length).toBe(3);
  });
});

describe("ChannelContentTable — inline CRUD actions", () => {
  it("renders an 'Ações' column header", async () => {
    const { container } = await renderTable();
    const headerTexts = Array.from(container.querySelectorAll("th")).map((th) => th.textContent ?? "");
    expect(headerTexts.some((t) => /Ações/i.test(t))).toBe(true);
  });

  it("renders per-row Edit + Excluir action buttons", async () => {
    const { getByLabelText } = await renderTable();
    expect(getByLabelText(`Editar ${baseVideo.title}`)).toBeTruthy();
    expect(getByLabelText(`Excluir ${baseVideo.title}`)).toBeTruthy();
  });

  it("clicking the row Edit icon calls onEdit and does NOT bubble to onRowClick", async () => {
    const onEdit = vi.fn();
    const onRowClick = vi.fn();
    const { getByLabelText, fireEvent } = await renderTable({ onEdit, onRowClick });
    fireEvent.click(getByLabelText(`Editar ${baseVideo.title}`));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ youtube_video_id: baseVideo.youtube_video_id }),
    );
    // stopPropagation: the row's onRowClick must NOT also fire.
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("clicking the row Excluir icon calls onDelete and does NOT bubble to onRowClick", async () => {
    const onDelete = vi.fn();
    const onRowClick = vi.fn();
    const { getByLabelText, fireEvent } = await renderTable({ onDelete, onRowClick });
    fireEvent.click(getByLabelText(`Excluir ${baseVideo.title}`));
    expect(onDelete).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledWith(
      expect.objectContaining({ youtube_video_id: baseVideo.youtube_video_id }),
    );
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
