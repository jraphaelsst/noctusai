/**
 * Dashboard hooks — three independent fetches so a slow panel doesn't
 * block the rest from rendering.
 *
 *   useDashboardStats    → top-row KPI tiles
 *   useTopVideos         → top-5 videos panel
 *   useRecentUploads     → recent uploads + delivery status panel
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@noctusai/seed/infra";
import { toast } from "sonner";

import { useActiveAccountId } from "@/state/useActiveAccount";

// ─── Types (mirror backend schemas) ────────────────────────────────────
export interface KpiStats {
  total_videos: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  last_synced_at: string | null;
  channel_id: string | null;
  channel_title: string | null;
}

export interface TopVideo {
  youtube_video_id: string;
  title: string | null;
  thumbnail_url: string | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  published_at: string | null;
  duration: string | null;
  uploaded_via_app: boolean;
}

export type NotificationDeliveryStatus =
  | "none"
  | "all_sent"
  | "partial"
  | "all_failed";

export interface RecentUpload {
  job_id: string;
  youtube_video_id: string | null;
  title: string;
  status: string;
  privacy_status: string | null;
  product_code: string | null;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  notification_status: NotificationDeliveryStatus;
  notification_attempts: number;
  notification_succeeded: number;
  notification_failed: number;
}

export interface QueueEntry {
  position: number;
  job_id: string;
  enqueued_at: number;
  title: string | null;
  product_code: string | null;
  status: string | null;
}

export interface QueueState {
  max_concurrent: number;
  entries: QueueEntry[];
  total: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function withAccountId(base: string, accountId?: string | null): string {
  if (!accountId) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}account_id=${encodeURIComponent(accountId)}`;
}

// ─── Hooks ─────────────────────────────────────────────────────────────
export function useDashboardStats(accountId?: string | null) {
  const [data, setData] = useState<KpiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const storeAccountId = useActiveAccountId("youtube");
  const effectiveAccountId = accountId ?? storeAccountId;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const stats = await api.get<KpiStats>(
        withAccountId("/api/dashboard/stats", effectiveAccountId),
      );
      setData(stats);
    } catch (err: any) {
      setError(err?.message ?? "Falha ao carregar dashboard");
    } finally {
      setLoading(false);
    }
  }, [effectiveAccountId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}

export function useTopVideos(limit = 5, accountId?: string | null) {
  const [data, setData] = useState<TopVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const storeAccountId = useActiveAccountId("youtube");
  const effectiveAccountId = accountId ?? storeAccountId;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get<TopVideo[]>(
      withAccountId(`/api/dashboard/top-videos?limit=${limit}`, effectiveAccountId),
    )
      .then((rows) => { if (!cancelled) setData(rows); })
      .catch((err) => {
        if (cancelled) return;
        console.error("top videos load failed", err);
        toast.error(err?.message ?? "Falha ao carregar top videos");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [limit, effectiveAccountId]);

  return { data, loading };
}

export function useRecentUploads(limit = 10, accountId?: string | null) {
  const [data, setData] = useState<RecentUpload[]>([]);
  const [loading, setLoading] = useState(true);
  const storeAccountId = useActiveAccountId("youtube");
  const effectiveAccountId = accountId ?? storeAccountId;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.get<RecentUpload[]>(
        withAccountId(`/api/dashboard/recent-uploads?limit=${limit}`, effectiveAccountId),
      );
      setData(rows);
    } catch (err: any) {
      console.error("recent uploads load failed", err);
      toast.error(err?.message ?? "Falha ao carregar envios recentes");
    } finally {
      setLoading(false);
    }
  }, [limit, effectiveAccountId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, refresh };
}

// ─── Retry a failed upload job ────────────────────────────────────────
// Hits POST /api/videos/upload/{job_id}/retry. The backend re-queues
// the job and kicks `run_upload_job` in a background task. Returns the
// updated job row so the dashboard can flip its badge optimistically.
export async function retryUpload(jobId: string): Promise<void> {
  await api.post(`/api/videos/upload/${jobId}/retry`, {});
}

// ─── Queue state — live "what's in the pipeline" panel ───────────────
// Polls the dashboard's queue-state endpoint every N seconds (caller
// controls the cadence). Each entry has the upload's queue position +
// job metadata so the operator can see who's running and who's
// waiting.
export function useQueueState(intervalMs = 5000) {
  const [data, setData] = useState<QueueState | null>(null);

  const refresh = useCallback(async () => {
    try {
      const state = await api.get<QueueState>("/api/dashboard/queue-state");
      setData(state);
    } catch (err) {
      // Empty queue + Redis errors degrade silently — the panel just
      // hides itself rather than showing an alarming red error.
      setData({ max_concurrent: 1, entries: [], total: 0 });
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), intervalMs);
    return () => window.clearInterval(id);
  }, [refresh, intervalMs]);

  return { data, refresh };
}

// ─── Helpers exposed to consumers ──────────────────────────────────────
// Re-exported from the shared util (DRY — see @/lib/formatNumber for why).
export { formatNumber } from "@/lib/formatNumber";
