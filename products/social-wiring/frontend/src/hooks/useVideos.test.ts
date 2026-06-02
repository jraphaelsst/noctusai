/**
 * Tests for useUpdateVideo + useDeleteVideo hooks.
 *
 * Covers:
 *   · useUpdateVideo calls PATCH /api/videos/{id} with the right body
 *   · useUpdateVideo threads account_id from the store
 *   · useUpdateVideo shows a success toast on success
 *   · useUpdateVideo shows an error toast on failure
 *   · useDeleteVideo calls DELETE /api/videos/{id}
 *   · useDeleteVideo threads account_id from the store
 *   · useDeleteVideo shows a success toast on success
 *   · useDeleteVideo shows an error toast on failure
 *
 * Mock strategy mirrors useIntegrationAccounts.test.ts:
 *   · @noctusai/seed/infra — mocked at the module level.
 *   · @tanstack/react-query — minimal stub (useMutation runs mutationFn then onSuccess).
 *   · sonner/toast — mocked to capture toast calls.
 *   · useActiveAccountStore — mocked to control the active account.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ─── Hoisted mocks ─────────────────────────────────────────────────────────
const { mockPatch, mockDelete, toastSuccess, toastError, mockActiveAccountId } =
  vi.hoisted(() => ({
    mockPatch: vi.fn(),
    mockDelete: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
    mockActiveAccountId: { value: null as string | null },
  }));

vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: mockPatch,
    delete: mockDelete,
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: toastSuccess,
    error: toastError,
  },
}));

vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountStore: vi.fn((selector: (s: any) => any) =>
    selector({ activeAccountId: mockActiveAccountId.value }),
  ),
}));

vi.mock("@tanstack/react-query", () => {
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
      onError,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown) => void;
      onError?: (e: unknown) => void;
    }) => ({
      mutateAsync: async (vars: unknown) => {
        try {
          const result = await mutationFn(vars);
          onSuccess?.(result);
          return result;
        } catch (err) {
          onError?.(err);
          throw err;
        }
      },
      mutate: async (vars: unknown) => {
        try {
          const result = await mutationFn(vars);
          onSuccess?.(result);
          return result;
        } catch (err) {
          onError?.(err);
        }
      },
      isPending: false,
    }),
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useMutation, useQueryClient };
});

import { useUpdateVideo, useDeleteVideo } from "./useVideos";

beforeEach(() => {
  vi.clearAllMocks();
  mockActiveAccountId.value = null;
});

// ─── useUpdateVideo ──────────────────────────────────────────────────────────

describe("useUpdateVideo", () => {
  it("calls PATCH /api/videos/{id} with the correct body", async () => {
    const updatedVideo = {
      id: "row-1",
      youtube_video_id: "abc123",
      title: "New Title",
      description: "New desc",
      privacy_status: "unlisted" as const,
      view_count: 0,
      like_count: 0,
      comment_count: 0,
      favorite_count: 0,
      tags: [],
      uploaded_via_app: false,
      synced_at: "2026-06-01T00:00:00Z",
    };
    mockPatch.mockResolvedValue(updatedVideo);

    const hook = useUpdateVideo() as any;
    await hook.mutateAsync({
      youtubeVideoId: "abc123",
      body: { title: "New Title", privacy_status: "unlisted" },
    });

    expect(mockPatch).toHaveBeenCalledWith(
      "/api/videos/abc123",
      { title: "New Title", privacy_status: "unlisted" },
    );
  });

  it("appends account_id query param when store has an active account", async () => {
    mockActiveAccountId.value = "acct-uuid-1";
    mockPatch.mockResolvedValue({ youtube_video_id: "vid1", synced_at: "2026-01-01" });

    const hook = useUpdateVideo() as any;
    await hook.mutateAsync({ youtubeVideoId: "vid1", body: { title: "T" } });

    expect(mockPatch).toHaveBeenCalledWith(
      "/api/videos/vid1?account_id=acct-uuid-1",
      { title: "T" },
    );
  });

  it("does NOT append account_id when store is null", async () => {
    mockActiveAccountId.value = null;
    mockPatch.mockResolvedValue({ youtube_video_id: "vid2", synced_at: "2026-01-01" });

    const hook = useUpdateVideo() as any;
    await hook.mutateAsync({ youtubeVideoId: "vid2", body: { description: "D" } });

    expect(mockPatch).toHaveBeenCalledWith(
      "/api/videos/vid2",
      { description: "D" },
    );
  });

  it("shows a success toast on success", async () => {
    mockPatch.mockResolvedValue({ youtube_video_id: "vid3", synced_at: "2026-01-01" });

    const hook = useUpdateVideo() as any;
    await hook.mutateAsync({ youtubeVideoId: "vid3", body: { title: "T" } });

    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining("atualizado"));
  });

  it("calls onSuccess callback with the updated video", async () => {
    const updatedVideo = { youtube_video_id: "vid4", synced_at: "2026-01-01" };
    mockPatch.mockResolvedValue(updatedVideo);

    const onSuccess = vi.fn();
    const hook = useUpdateVideo({ onSuccess }) as any;
    await hook.mutateAsync({ youtubeVideoId: "vid4", body: { title: "T" } });

    expect(onSuccess).toHaveBeenCalledWith(updatedVideo);
  });

  it("shows an error toast on failure", async () => {
    mockPatch.mockRejectedValue({ message: "YouTube API error" });

    const hook = useUpdateVideo() as any;
    try {
      await hook.mutateAsync({ youtubeVideoId: "vid5", body: { title: "T" } });
    } catch {
      // expected
    }

    expect(toastError).toHaveBeenCalledWith(
      expect.stringMatching(/YouTube API error|atualizar/),
    );
  });
});

// ─── useDeleteVideo ──────────────────────────────────────────────────────────

describe("useDeleteVideo", () => {
  it("calls DELETE /api/videos/{id}", async () => {
    mockDelete.mockResolvedValue(undefined);

    const hook = useDeleteVideo() as any;
    await hook.mutateAsync("abc123");

    expect(mockDelete).toHaveBeenCalledWith("/api/videos/abc123");
  });

  it("appends account_id when store has an active account", async () => {
    mockActiveAccountId.value = "acct-uuid-2";
    mockDelete.mockResolvedValue(undefined);

    const hook = useDeleteVideo() as any;
    await hook.mutateAsync("vid1");

    expect(mockDelete).toHaveBeenCalledWith("/api/videos/vid1?account_id=acct-uuid-2");
  });

  it("does NOT append account_id when store is null", async () => {
    mockActiveAccountId.value = null;
    mockDelete.mockResolvedValue(undefined);

    const hook = useDeleteVideo() as any;
    await hook.mutateAsync("vid2");

    expect(mockDelete).toHaveBeenCalledWith("/api/videos/vid2");
  });

  it("shows a success toast on success", async () => {
    mockDelete.mockResolvedValue(undefined);

    const hook = useDeleteVideo() as any;
    await hook.mutateAsync("vid3");

    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining("catálogo"));
  });

  it("calls onSuccess callback on success", async () => {
    mockDelete.mockResolvedValue(undefined);

    const onSuccess = vi.fn();
    const hook = useDeleteVideo({ onSuccess }) as any;
    await hook.mutateAsync("vid4");

    expect(onSuccess).toHaveBeenCalledOnce();
  });

  it("shows an error toast on failure", async () => {
    mockDelete.mockRejectedValue({ message: "Network error" });

    const hook = useDeleteVideo() as any;
    try {
      await hook.mutateAsync("vid5");
    } catch {
      // expected
    }

    expect(toastError).toHaveBeenCalledWith(
      expect.stringMatching(/Network error|remover/),
    );
  });
});
