/**
 * Videos hooks — wrap /api/videos/* read endpoints + the sync trigger.
 *
 *   useVideos     — paginated list (cursor-based "load more")
 *   useVideoSync  — POST /api/videos/sync; returns the SyncResult so the
 *                   UI can show "synced N videos in M pages"
 *   useUpdateVideo — PATCH /api/videos/{id}; write-through to YouTube +
 *                    catalog mirror; on success calls onSuccess to refresh
 *   useDeleteVideo — DELETE /api/videos/{id}; catalog-only removal;
 *                    on success calls onSuccess to refresh
 */
import { useCallback, useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { toast } from "sonner";

import { useActiveAccountStore } from "@/state/useActiveAccount";

// ─── Types (mirror backend schemas) ────────────────────────────────────
export type PrivacyStatus = "public" | "unlisted" | "private";

export interface Video {
  id: string;
  youtube_video_id: string;
  title?: string | null;
  description?: string | null;
  thumbnail_url?: string | null;
  published_at?: string | null;
  duration?: string | null;        // ISO-8601 (PT1M30S)
  privacy_status?: PrivacyStatus | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  favorite_count: number;
  tags: string[];
  category_id?: string | null;
  uploaded_via_app: boolean;
  synced_at: string;
}

export interface VideoListResponse {
  items: Video[];
  next_cursor: string | null;
  total_known: number;
}

export interface VideoSyncResult {
  inserted: number;
  updated: number;
  fetched: number;
  pages: number;
  quota_units_estimated: number;
  last_synced_at: string;
}

// ─── Helpers ───────────────────────────────────────────────────────────
export function youtubeUrl(videoId: string): string {
  return `https://www.youtube.com/watch?v=${videoId}`;
}

/**
 * Parse YouTube's ISO-8601 duration ("PT1M30S") into a "1:30" display
 * string. Returns the original on parse failure so the UI never blanks.
 */
export function formatDuration(iso?: string | null): string {
  if (!iso) return "";
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!match) return iso;
  const [, h, m, s] = match;
  const hours = parseInt(h ?? "0", 10);
  const mins = parseInt(m ?? "0", 10);
  const secs = parseInt(s ?? "0", 10);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hours > 0) return `${hours}:${pad(mins)}:${pad(secs)}`;
  return `${mins}:${pad(secs)}`;
}

export function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/** Parse an ISO-8601 duration ("PT1M30S") to whole seconds. 0 on failure. */
export function durationSeconds(iso?: string | null): number {
  if (!iso) return 0;
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!match) return 0;
  const [, h, m, s] = match;
  return (
    parseInt(h ?? "0", 10) * 3600 +
    parseInt(m ?? "0", 10) * 60 +
    parseInt(s ?? "0", 10)
  );
}

/**
 * Heuristic Shorts classifier for the catalog. `video_cache` carries no
 * explicit Shorts flag (only `duration`), so we treat clips ≤ 60s as Shorts
 * — the discriminator most operators expect. v1: when the upload pipeline
 * starts carrying `target_format` into the cache, switch to that flag.
 */
export function isShort(video: Pick<Video, "duration">): boolean {
  const secs = durationSeconds(video.duration);
  return secs > 0 && secs <= 60;
}

// ─── List hook ─────────────────────────────────────────────────────────
interface UseVideosOptions {
  pageSize?: number;
  uploadedViaApp?: boolean;
  /** When provided, fetches videos for a specific YouTube integration account. */
  accountId?: string | null;
  /**
   * Filter by video kind as stored on the BE.
   * "video" = long-form, "short" = YouTube Shorts.
   * When omitted the backend returns all kinds.
   */
  kind?: "video" | "short";
}

export function useVideos(options: UseVideosOptions = {}) {
  const { pageSize = 50, uploadedViaApp, accountId, kind } = options;
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  const effectiveAccountId = accountId ?? storeAccountId;
  const [items, setItems] = useState<Video[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [totalKnown, setTotalKnown] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildPath = useCallback(
    (next?: string | null): string => {
      const params = new URLSearchParams();
      params.set("limit", String(pageSize));
      if (next) params.set("cursor", next);
      if (uploadedViaApp !== undefined) {
        params.set("uploaded_via_app", String(uploadedViaApp));
      }
      if (effectiveAccountId) params.set("account_id", effectiveAccountId);
      if (kind) params.set("kind", kind);
      return `/api/videos?${params.toString()}`;
    },
    [pageSize, uploadedViaApp, effectiveAccountId, kind],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<VideoListResponse>(buildPath());
      setItems(response.items);
      setCursor(response.next_cursor);
      setTotalKnown(response.total_known);
    } catch (err: any) {
      setError(err?.message ?? "Falha ao carregar videos");
    } finally {
      setLoading(false);
    }
  }, [buildPath]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const response = await api.get<VideoListResponse>(buildPath(cursor));
      setItems((prev) => [...prev, ...response.items]);
      setCursor(response.next_cursor);
      setTotalKnown(response.total_known);
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao carregar mais");
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, loadingMore, buildPath]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    items,
    totalKnown,
    loading,
    loadingMore,
    error,
    hasMore: cursor !== null,
    refresh,
    loadMore,
  };
}

// ─── Update body type ───────────────────────────────────────────────────
export interface VideoUpdateBody {
  title?: string | null;
  description?: string | null;
  privacy_status?: PrivacyStatus | null;
}

// ─── Sync hook ─────────────────────────────────────────────────────────
export function useVideoSync(onComplete?: () => void) {
  const [pending, setPending] = useState(false);
  const [lastResult, setLastResult] = useState<VideoSyncResult | null>(null);
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);

  const sync = useCallback(async () => {
    setPending(true);
    try {
      const path = storeAccountId
        ? `/api/videos/sync?account_id=${encodeURIComponent(storeAccountId)}`
        : "/api/videos/sync";
      const result = await api.post<VideoSyncResult>(path);
      setLastResult(result);
      const total = result.inserted + result.updated;
      toast.success(
        `${total} videos sincronizados (${result.pages} paginas, ~${result.quota_units_estimated} unidades de quota)`,
      );
      onComplete?.();
      return result;
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao sincronizar com o YouTube");
      throw err;
    } finally {
      setPending(false);
    }
  }, [onComplete]);

  return { sync, pending, lastResult };
}

// ─── Update hook ────────────────────────────────────────────────────────
/**
 * useUpdateVideo — PATCH /api/videos/{youtube_video_id}
 *
 * Write-through to YouTube (title / description / privacy_status) then
 * mirrors the change to the local catalog. All fields are optional.
 * Threads ``account_id`` from ``useActiveAccountStore`` like the other hooks.
 *
 * Usage:
 *   const { mutate: updateVideo, isPending } = useUpdateVideo({ onSuccess: refresh });
 *   updateVideo({ youtubeVideoId: "abc", body: { title: "New title" } });
 */
export function useUpdateVideo(options?: { onSuccess?: (updated: Video) => void }) {
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);

  return useMutation({
    mutationFn: async ({
      youtubeVideoId,
      body,
    }: {
      youtubeVideoId: string;
      body: VideoUpdateBody;
    }): Promise<Video> => {
      const params = storeAccountId
        ? `?account_id=${encodeURIComponent(storeAccountId)}`
        : "";
      return api.patch<Video>(`/api/videos/${encodeURIComponent(youtubeVideoId)}${params}`, body);
    },
    onSuccess: (updated) => {
      toast.success("Video atualizado com sucesso");
      options?.onSuccess?.(updated);
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao atualizar o video");
    },
  });
}

// ─── Delete hook ────────────────────────────────────────────────────────

/** Options for a delete call. ``purgeRemote`` is opt-in; the default is
 * catalog-only (safe, re-syncable). */
export interface DeleteVideoOptions {
  youtubeVideoId: string;
  /** When true, PERMANENTLY deletes the video from YouTube (irreversible).
   * Defaults to false (catalog-only removal). */
  purgeRemote?: boolean;
}

/**
 * useDeleteVideo — DELETE /api/videos/{youtube_video_id}
 *
 * Two modes, controlled by ``purgeRemote``:
 * - ``false`` (default): catalog-only removal — the real YouTube video is
 *   NOT affected. The row can be recovered via POST /api/videos/sync.
 * - ``true``: PERMANENTLY deletes the video from YouTube (irreversible —
 *   no undo) and then removes the catalog row. Requires an explicit
 *   operator double-confirmation before calling with this flag.
 *
 * Threads ``account_id`` from ``useActiveAccountStore`` like the other hooks.
 *
 * Usage:
 *   const { mutate: deleteVideo, isPending } = useDeleteVideo({ onSuccess: refresh });
 *   // catalog-only:
 *   deleteVideo({ youtubeVideoId: "dQw4w9WgXcQ" });
 *   // permanent YouTube delete:
 *   deleteVideo({ youtubeVideoId: "dQw4w9WgXcQ", purgeRemote: true });
 */
export function useDeleteVideo(options?: { onSuccess?: () => void }) {
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);

  return useMutation({
    mutationFn: async ({ youtubeVideoId, purgeRemote = false }: DeleteVideoOptions): Promise<boolean> => {
      const params = new URLSearchParams();
      if (storeAccountId) params.set("account_id", storeAccountId);
      if (purgeRemote) params.set("purge_remote", "true");
      const qs = params.toString() ? `?${params.toString()}` : "";
      await api.delete(`/api/videos/${encodeURIComponent(youtubeVideoId)}${qs}`);
      // Return purgeRemote so onSuccess can show the correct toast without
      // depending on the `variables` arg (which some mutation stubs don't forward).
      return purgeRemote;
    },
    onSuccess: (wasPurged: boolean) => {
      if (wasPurged) {
        toast.success("Video excluído permanentemente do YouTube");
      } else {
        toast.success("Video removido do catálogo");
      }
      options?.onSuccess?.();
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao remover o video");
    },
  });
}
