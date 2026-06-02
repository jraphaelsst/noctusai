/**
 * useChannelTrend — fetches channel-level subscriber/view/video-count snapshots.
 *
 * Endpoint: GET /api/youtube/channel/trend?account_id=&days=30
 * Returns:  { points: [{ snapshot_date, subscriber_count, view_count, video_count }] }
 *
 * Defaults accountId from the shared useActiveAccountStore so switching the
 * account switcher automatically re-fetches the correct channel's trend.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@noctusai/seed/infra";
import { useActiveAccountStore } from "@/state/useActiveAccount";

export interface ChannelTrendPoint {
  snapshot_date: string;
  subscriber_count: number;
  view_count: number;
  video_count: number;
}

export interface ChannelTrendResponse {
  points: ChannelTrendPoint[];
}

export function useChannelTrend(days = 30, accountId?: string | null) {
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  const effectiveAccountId = accountId ?? storeAccountId;

  const [data, setData] = useState<ChannelTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const buildPath = useCallback((): string => {
    const params = new URLSearchParams({ days: String(days) });
    if (effectiveAccountId) params.set("account_id", effectiveAccountId);
    return `/api/youtube/channel/trend?${params.toString()}`;
  }, [days, effectiveAccountId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<ChannelTrendResponse>(buildPath());
      setData(res.points ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Falha ao carregar tendência do canal");
    } finally {
      setLoading(false);
    }
  }, [buildPath]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}
