/**
 * useInstagramInsights — TanStack Query wrappers for the Instagram Business
 * Login insights API (`/api/instagram/accounts/{account_id}/...`).
 *
 * Contract: products/social-wiring/projects/core-studio/specs/instagram-insights-api.md
 *
 * GET routes read OUR stored data (never Graph). `null` means Meta did not
 * serve the metric — it is never coerced to 0; the UI renders "—".
 *
 * Loading signals are derived by the consumers off `data`
 * (`showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`)
 * → KB § PATTERNS/frontend/lying-loading-state.md
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";
import { api } from "@noctusai/seed/infra";

import { useIntegrationAccounts, type IntegrationAccount } from "@/hooks/useIntegrationAccounts";
import { useActiveAccountId } from "@/state/useActiveAccount";

export const INSTAGRAM_PROVIDER = "instagram";

// ─── Types ──────────────────────────────────────────────────────────────────

export type InstagramMetricFormat = "int" | "duration_ms" | "percent";

export interface InstagramMetricDef {
  key: string;
  label: string;
  format: InstagramMetricFormat;
  /** 1 = most relevant. */
  priority: number;
}

export interface InstagramProfile {
  account_id: string;
  marca_id: string | null;
  ig_user_id: string | null;
  username: string | null;
  name: string | null;
  profile_picture_url: string | null;
  followers_count: number | null;
  follows_count: number | null;
  media_count: number | null;
  biography: string | null;
  website: string | null;
  last_synced_at: string | null;
  insights_scope_granted: boolean;
}

export interface InstagramTrendPoint {
  date: string;
  [metricKey: string]: number | string | null | undefined;
}

export interface InstagramTrend {
  points: InstagramTrendPoint[];
  metrics: InstagramMetricDef[];
}

export interface InstagramMediaItem {
  id: string;
  media_type: "IMAGE" | "VIDEO" | "CAROUSEL_ALBUM" | null;
  media_product_type: "FEED" | "REELS" | "STORY" | "AD" | null;
  caption: string | null;
  permalink: string | null;
  thumbnail_url: string | null;
  media_url: string | null;
  timestamp: string;
  like_count: number | null;
  comments_count: number | null;
  latest: Record<string, number | null> | null;
  latest_snapshot_date: string | null;
  synced_at: string;
}

export interface InstagramMediaPage {
  items: InstagramMediaItem[];
  next_cursor: string | null;
}

export interface InstagramMediaHistory {
  media: InstagramMediaItem;
  points: InstagramTrendPoint[];
  metrics: InstagramMetricDef[];
}

export interface InstagramSyncOk {
  status: "done" | "partial" | "skipped";
  snapshot_date: string;
  media_synced: number;
  stories_synced: number;
  snapshots_written: number;
  profile_snapshot_written: boolean;
  media_failed: number;
  media_skipped: number;
  errors: string[];
}

export interface InstagramSyncReconnect {
  requires_reconnect: true;
  missing_scopes?: string[];
  error?: string | null;
}

export interface InstagramSyncAppReview {
  requires_app_review: true;
  error?: string | null;
}

export type InstagramSyncResult =
  | InstagramSyncOk
  | InstagramSyncReconnect
  | InstagramSyncAppReview;

export function isSyncReconnect(x: unknown): x is InstagramSyncReconnect {
  return !!x && typeof x === "object" && (x as InstagramSyncReconnect).requires_reconnect === true;
}
export function isSyncAppReview(x: unknown): x is InstagramSyncAppReview {
  return !!x && typeof x === "object" && (x as InstagramSyncAppReview).requires_app_review === true;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const FAMILY = ["sw", "instagram"] as const;
const PROFILE_KEY = (id: string | null) => [...FAMILY, "profile", id] as const;
const TREND_KEY = (id: string | null, days: number) => [...FAMILY, "trend", id, days] as const;
const MEDIA_KEY = (id: string | null, limit: number) => [...FAMILY, "media", id, limit] as const;
const HISTORY_KEY = (id: string | null, mediaId: string | null, days: number) =>
  [...FAMILY, "history", id, mediaId, days] as const;

const base = (accountId: string) => `/api/instagram/accounts/${accountId}`;

// ─── Account resolution ─────────────────────────────────────────────────────

/**
 * The active Instagram-Login account: the switcher's selection when it still
 * exists, else the only/first connected account. (The switcher auto-selects
 * when exactly one account is in scope; this covers the render before its
 * effect commits and the multi-account "nothing picked yet" state.)
 */
export function useActiveInstagramAccount() {
  const accountsQuery = useIntegrationAccounts({ provider: INSTAGRAM_PROVIDER });
  const activeId = useActiveAccountId(INSTAGRAM_PROVIDER);
  const accounts: IntegrationAccount[] = accountsQuery.data ?? [];
  const account = accounts.find((a) => a.id === activeId) ?? accounts[0] ?? null;
  return {
    accountId: account?.id ?? null,
    account,
    accounts,
    isPending: accountsQuery.isPending && !accountsQuery.data,
    isError: accountsQuery.isError && !accountsQuery.data,
  };
}

// ─── Reads ──────────────────────────────────────────────────────────────────

// No `placeholderData: prev` below: every key embeds an account id, and one
// account's profile/posts must never be painted under another's header while
// the switch refetches (authorization-scoped personal data).

export function useInstagramProfile(accountId: string | null) {
  return useQuery<InstagramProfile>({
    queryKey: PROFILE_KEY(accountId),
    queryFn: () => api.get<InstagramProfile>(`${base(accountId as string)}/profile`),
    enabled: !!accountId,
  });
}

export function useInstagramTrend(accountId: string | null, days = 30) {
  return useQuery<InstagramTrend>({
    queryKey: TREND_KEY(accountId, days),
    queryFn: () =>
      api.get<InstagramTrend>(`${base(accountId as string)}/profile/trend?days=${days}`),
    enabled: !!accountId,
  });
}

/** Newest → oldest, server keyset pagination ("Carregar mais"). */
export function useInstagramMedia(accountId: string | null, limit = 24) {
  return useInfiniteQuery<InstagramMediaPage>({
    queryKey: MEDIA_KEY(accountId, limit),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (pageParam) qs.set("cursor", String(pageParam));
      return api.get<InstagramMediaPage>(`${base(accountId as string)}/media?${qs.toString()}`);
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!accountId,
  });
}

export function useInstagramMediaHistory(
  accountId: string | null,
  mediaId: string | null,
  days = 90,
) {
  return useQuery<InstagramMediaHistory>({
    queryKey: HISTORY_KEY(accountId, mediaId, days),
    queryFn: () =>
      api.get<InstagramMediaHistory>(
        `${base(accountId as string)}/media/${encodeURIComponent(mediaId as string)}/insights/history?days=${days}`,
      ),
    enabled: !!accountId && !!mediaId,
  });
}

// ─── Sync ───────────────────────────────────────────────────────────────────

/**
 * POST …/sync. A 409 `{requires_reconnect}` is a NORMAL outcome (resolves
 * with the gate body, like `requires_app_review`), so the UI renders the
 * "Reconectar" CTA from `data` instead of a generic error toast. Any other
 * failure (502 etc.) still rejects.
 */
export function useInstagramSync(accountId: string | null) {
  const qc = useQueryClient();
  return useMutation<InstagramSyncResult, unknown, { force?: boolean } | void>({
    mutationFn: async (opts) => {
      try {
        return await api.post<InstagramSyncResult>(
          `${base(accountId as string)}/sync${opts && opts.force ? "?force=true" : ""}`,
          {},
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          const body = err.body as Record<string, unknown> | undefined;
          const gate = (body && typeof body.detail === "object" && body.detail ? body.detail : body) as
            | Partial<InstagramSyncReconnect>
            | undefined;
          return { ...gate, requires_reconnect: true } as InstagramSyncReconnect;
        }
        throw err;
      }
    },
    onSuccess: (res) => {
      if (isSyncReconnect(res) || isSyncAppReview(res)) return;
      qc.invalidateQueries({ queryKey: FAMILY });
    },
  });
}
