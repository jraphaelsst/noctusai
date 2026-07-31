/**
 * useVideoTrend — fetches per-video view/like/comment-count snapshots.
 *
 * Endpoint: GET /api/youtube/videos/{youtube_video_id}/trend?account_id=
 * Returns:  { points: [{ snapshot_date, view_count, like_count, comment_count }] }
 *
 * Defaults accountId from the shared useActiveAccountStore.
 * Only fetches when `videoId` is non-null (null = modal closed).
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@noctusai/seed/infra";
import { useActiveAccountId } from "@/state/useActiveAccount";

export interface VideoTrendPoint {
  snapshot_date: string;
  view_count: number;
  like_count: number;
  comment_count: number;
}

export interface VideoTrendResponse {
  points: VideoTrendPoint[];
}

export function useVideoTrend(videoId: string | null, accountId?: string | null) {
  const storeAccountId = useActiveAccountId("youtube");
  const effectiveAccountId = accountId ?? storeAccountId;

  const [data, setData] = useState<VideoTrendPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildPath = useCallback(
    (vid: string): string => {
      const params = new URLSearchParams();
      if (effectiveAccountId) params.set("account_id", effectiveAccountId);
      const qs = params.toString();
      return `/api/youtube/videos/${encodeURIComponent(vid)}/trend${qs ? `?${qs}` : ""}`;
    },
    [effectiveAccountId],
  );

  useEffect(() => {
    if (!videoId) {
      setData([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<VideoTrendResponse>(buildPath(videoId))
      .then((res) => {
        if (!cancelled) setData(res.points ?? []);
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message ?? "Falha ao carregar tendência do vídeo");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [videoId, buildPath]);

  return { data, loading, error };
}
