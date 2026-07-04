/**
 * Instagram insights hooks — TanStack Query wrappers over
 * `/api/meta/instagram/*` (contract: projects/ig-insights-fe/CONTRACT.md).
 *
 * Mirrors useMailchimpConnection.ts / useIntegrationAccounts.ts conventions:
 *   · const KEY per query key, all under a shared family
 *   · api.get / api.post from @noctusai/seed/infra
 *   · mutations invalidate the relevant family key on success
 *
 * `org_id` is optional on every endpoint (backend falls back to
 * `settings.local_dev_org_id` when omitted) — social-wiring has no
 * per-request org context wired for the Meta surface yet, so every
 * hook here omits it, same posture as `/api/meta/status` and
 * `/api/mailchimp/connection`.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types (mirror app/routers/meta_router.py + meta_insights_router.py) ────

export interface MetaStatus {
  configured: boolean;
  adapter: "oauth" | "fake" | string;
  auth_mode: string;
  consent_required: boolean;
  user_id: string | null;
  user_name: string | null;
  pages_count: number;
  instagram_accounts_count: number;
  error: string | null;
}

export interface IGAccount {
  id: string;
  username: string;
  name?: string | null;
  profile_picture_url?: string | null;
  followers_count?: number | null;
  follows_count?: number | null;
  media_count?: number | null;
  biography?: string | null;
  website?: string | null;
  page_id?: string | null;
}

export interface IGAccountsResponse {
  accounts: IGAccount[];
  adapter: string;
}

export interface IGInsights {
  object_id: string;
  metrics: Record<string, number>;
  series: unknown[];
  error?: string | null;
}

export interface IGMediaItem {
  id: string;
  caption?: string | null;
  media_type?: string | null;
  permalink?: string | null;
  thumbnail_url?: string | null;
  timestamp?: string | null;
  like_count: number;
  comments_count: number;
  insights: Record<string, number> | null;
}

export interface IGMediaResponse {
  media: IGMediaItem[];
}

export interface IGSnapshot {
  captured_at: string;
  followers_count?: number | null;
  follows_count?: number | null;
  media_count?: number | null;
  reach?: number | null;
  profile_views?: number | null;
}

export interface IGSnapshotsResponse {
  snapshots: IGSnapshot[];
}

// ─── Query keys ──────────────────────────────────────────────────────────────

const FAMILY_KEY = ["ig-insights"] as const;
const STATUS_KEY = ["meta", "status"] as const;
const ACCOUNTS_KEY = [...FAMILY_KEY, "accounts"] as const;
const INSIGHTS_KEY = (igUserId: string, days: number) =>
  [...FAMILY_KEY, "insights", igUserId, days] as const;
const MEDIA_KEY = (igUserId: string, limit: number) =>
  [...FAMILY_KEY, "media", igUserId, limit] as const;
const SNAPSHOTS_KEY = (igUserId: string, days: number) =>
  [...FAMILY_KEY, "snapshots", igUserId, days] as const;

const BASE = "/api/meta/instagram";

// ─── Queries ─────────────────────────────────────────────────────────────────

/** Always-200 probe (mirrors /api/mailchimp/connection). adapter=="fake" or
 * consent_required=="true" means the "Conectar Instagram" CTA should show. */
export function useMetaStatus() {
  return useQuery<MetaStatus>({
    queryKey: STATUS_KEY,
    queryFn: () => api.get<MetaStatus>("/api/meta/status"),
    staleTime: 30_000,
  });
}

export function useIgAccounts(enabled = true) {
  return useQuery<IGAccountsResponse>({
    queryKey: ACCOUNTS_KEY,
    queryFn: () => api.get<IGAccountsResponse>(`${BASE}/accounts`),
    enabled,
  });
}

export function useIgInsights(igUserId: string | null, days = 30) {
  return useQuery<IGInsights>({
    queryKey: INSIGHTS_KEY(igUserId ?? "", days),
    queryFn: () =>
      api.get<IGInsights>(
        `${BASE}/${igUserId}/insights?period=day&days=${days}`,
      ),
    enabled: !!igUserId,
  });
}

export function useIgMedia(igUserId: string | null, limit = 25) {
  return useQuery<IGMediaResponse>({
    queryKey: MEDIA_KEY(igUserId ?? "", limit),
    queryFn: () =>
      api.get<IGMediaResponse>(
        `${BASE}/${igUserId}/media?limit=${limit}&with_insights=true`,
      ),
    enabled: !!igUserId,
  });
}

export function useIgSnapshots(igUserId: string | null, days = 90) {
  return useQuery<IGSnapshotsResponse>({
    queryKey: SNAPSHOTS_KEY(igUserId ?? "", days),
    queryFn: () =>
      api.get<IGSnapshotsResponse>(`${BASE}/${igUserId}/snapshots?days=${days}`),
    enabled: !!igUserId,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

/** "Capturar agora" — POST /snapshot then invalidate every /snapshots query
 * in the family (the caller doesn't need to know the exact days window). */
export function useCaptureIgSnapshot(igUserId: string | null) {
  const qc = useQueryClient();
  return useMutation<IGSnapshot, unknown, void>({
    mutationFn: () => api.post<IGSnapshot>(`${BASE}/${igUserId}/snapshot`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FAMILY_KEY });
    },
  });
}
