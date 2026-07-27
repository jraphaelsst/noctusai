/**
 * Meta Ads console hooks — TanStack Query wrappers over the `/api/meta/ads/*`
 * router (roadmap `meta-ads-console-2026-07`, W4).
 *
 * Unlike the Instagram/Facebook `useMeta` hooks, the ads surface is NOT
 * per-connection: it reads the SINGLE workspace-configured System-User ad
 * account (`settings.meta_ad_account_id`), so no `account_id` is threaded —
 * the backend resolves the account itself. When the account is not
 * configured every route 503s, and the hooks surface that so the UI can
 * render an actionable "não configurado" state (never a zeros dashboard).
 *
 * Money is ALWAYS integer cents on the wire (`*_cents`); format at display
 * via `@/lib/formatCurrency`. `since`/`until` are `YYYY-MM-DD` strings.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";
import { apiBase } from "@/lib/apiBase";

// ─── qs (local copy — mirrors useMeta's helper) ─────────────────────────────
function qs(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// ─── Types (mirror the backend Ads*Out DTOs verbatim) ───────────────────────

export interface AdsAccount {
  act_id: string;
  name: string | null;
  currency: string | null;
  timezone_name: string | null;
  amount_spent_cents: number | null;
  balance_cents: number | null;
  spend_cap_cents: number | null;
  account_status: number | null;
}
export interface AdsAccountsList {
  data: AdsAccount[];
}

export interface AdsCampaignLatest {
  date: string;
  spend_cents: number | null;
  impressions: number | null;
  clicks: number | null;
  reach: number | null;
  leads: number | null;
}
export interface AdsCampaign {
  object_id: string;
  name: string | null;
  objective: string | null;
  status: string | null;
  effective_status: string | null;
  daily_budget_cents: number | null;
  lifetime_budget_cents: number | null;
  latest: AdsCampaignLatest | null;
}
export interface AdsCampaignsList {
  data: AdsCampaign[];
}

export interface AdsObject {
  object_id: string;
  level: string;
  parent_id: string | null;
  name: string | null;
  status: string | null;
  effective_status: string | null;
  daily_budget_cents: number | null;
  optimization_goal: string | null;
  creative_id: string | null;
  creative_thumbnail_url: string | null;
}
export interface AdsObjectsList {
  data: AdsObject[];
}

export interface AdsInsightsRow {
  date: string;
  spend_cents: number | null;
  impressions: number | null;
  reach: number | null;
  clicks: number | null;
  cpc_cents: number | null;
  cpm_cents: number | null;
  ctr: number | null;
  actions: Record<string, number>;
  action_values: Record<string, number>;
  breakdown: Record<string, string>;
}
export interface AdsInsightsSeries {
  object_id: string;
  level: string;
  rows: AdsInsightsRow[];
}

export interface AdsTotals {
  spend_cents: number;
  impressions: number;
  reach: number;
  clicks: number;
  leads: number;
}
export interface AdsDelta {
  abs: number;
  pct: number | null;
}
export interface AdsInsightsCompare {
  current: AdsTotals;
  previous: AdsTotals;
  deltas: Record<string, AdsDelta>;
}

export interface AdsAccountDaily {
  date: string;
  spend_cents: number;
  impressions: number;
  reach: number;
  clicks: number;
  leads: number;
}
export interface AdsAccountInsights {
  since: string;
  until: string;
  totals: AdsTotals;
  actions: Record<string, number>;
  daily: AdsAccountDaily[];
}

export interface AdsPacingRow {
  object_id: string;
  name: string | null;
  effective_daily_budget_cents: number;
  budget_source: "campaign" | "adset_rollup";
  latest_spend_cents: number | null;
  latest_date: string | null;
}
export interface AdsPacingList {
  data: AdsPacingRow[];
}

export interface AdsActivity {
  object_id: string | null;
  object_level: string | null;
  event_type: string | null;
  occurred_at: string;
  actor_name: string | null;
  old_value: string | null;
  new_value: string | null;
}
export interface AdsActivitiesList {
  data: AdsActivity[];
}

// ─── Lead-ads (Instant Form) ────────────────────────────────────────────
export interface LeadgenQuestion {
  key: string | null;
  label: string | null;
  type: string | null;
  options: { key: string; value: string }[];
}
export interface LeadgenForm {
  form_id: string;
  name: string | null;
  status: string | null;
  locale: string | null;
  leads_count: number | null;
  created_time: string | null;
  page_id: string | null;
  page_name: string | null;
  questions: LeadgenQuestion[];
}
export interface LeadFormsSummary {
  total_leads: number;
  forms_count: number;
  active_forms: number;
  forms_with_leads: number;
  pages: { id: string; name: string }[];
  records_available: boolean;
  forms: LeadgenForm[];
  source: "db" | "live";
  stored_leads: number;
  last_synced_at: string | null;
}
export interface LeadField {
  name: string | null;
  values: string[];
}
export interface LeadRecord {
  id: string;
  created_time: string | null;
  ad_id: string | null;
  ad_name: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  platform: string | null;
  is_organic: boolean | null;
  field_data: LeadField[];
}
export interface LeadRecords {
  form_id: string;
  gated: boolean;
  reason: string | null;
  data: LeadRecord[];
  source: "db" | "live";
}

export interface AdsSyncStarted {
  job_id: string;
}
export interface AdsSyncStatus {
  job_id: string;
  status: string;
  detail: string | null;
}

export type AdsLevel = "campaign" | "adset" | "ad";

// ─── Query keys ─────────────────────────────────────────────────────────────
const K = {
  account: ["meta-ads", "account"] as const,
  campaigns: (status?: string, objective?: string) =>
    ["meta-ads", "campaigns", status ?? "", objective ?? ""] as const,
  children: (objectId: string, level: string) =>
    ["meta-ads", "children", objectId, level] as const,
  series: (id: string, level: string, since: string, until: string, bd?: string) =>
    ["meta-ads", "series", id, level, since, until, bd ?? ""] as const,
  compare: (id: string, level: string, since: string, until: string) =>
    ["meta-ads", "compare", id, level, since, until] as const,
  activities: (objectId: string | null, since: string, until: string) =>
    ["meta-ads", "activities", objectId ?? "", since, until] as const,
};

// ─── Hooks ──────────────────────────────────────────────────────────────────

/** The single configured ad account (or a 503 the UI turns into a
 *  "não configurado" state). */
export function useAdsAccount() {
  return useQuery<AdsAccountsList>({
    queryKey: K.account,
    queryFn: () => api.get<AdsAccountsList>("/api/meta/ads/accounts"),
  });
}

export function useAdsCampaigns(status?: string, objective?: string) {
  return useQuery<AdsCampaignsList>({
    queryKey: K.campaigns(status, objective),
    queryFn: () =>
      api.get<AdsCampaignsList>(
        `/api/meta/ads/campaigns${qs({ status, objective })}`,
      ),
  });
}

export function useAdsChildren(
  objectId: string | null,
  level: "adset" | "ad",
) {
  return useQuery<AdsObjectsList>({
    queryKey: K.children(objectId ?? "", level),
    queryFn: () =>
      api.get<AdsObjectsList>(
        `/api/meta/ads/campaigns/${encodeURIComponent(objectId ?? "")}/children${qs(
          { level },
        )}`,
      ),
    enabled: !!objectId,
  });
}

export function useAdsInsightsSeries(
  objectId: string | null,
  level: AdsLevel,
  since: string,
  until: string,
  breakdown?: string,
) {
  return useQuery<AdsInsightsSeries>({
    queryKey: K.series(objectId ?? "", level, since, until, breakdown),
    queryFn: () =>
      api.get<AdsInsightsSeries>(
        `/api/meta/ads/insights/series${qs({
          object_id: objectId,
          level,
          since,
          until,
          breakdown,
        })}`,
      ),
    enabled: !!objectId && !!since && !!until,
  });
}

/** Budget pacing for active campaigns — server resolves the EFFECTIVE
 *  daily budget (campaign-level for CBO, or a summed active-ad-set
 *  rollup for ABO) so the card populates even when the budget lives on
 *  the ad set, not the campaign. */
export function useAdsPacing() {
  return useQuery<AdsPacingList>({
    queryKey: ["meta-ads", "pacing"],
    queryFn: () => api.get<AdsPacingList>("/api/meta/ads/insights/pacing"),
  });
}

/** Account-level period aggregate — ONE request, server-side sum across
 *  all campaigns (replaces the per-campaign client fan-out). */
export function useAdsAccountInsights(since: string, until: string) {
  return useQuery<AdsAccountInsights>({
    queryKey: ["meta-ads", "account-insights", since, until],
    queryFn: () =>
      api.get<AdsAccountInsights>(
        `/api/meta/ads/insights/account${qs({ since, until })}`,
      ),
    enabled: !!since && !!until,
  });
}

export function useAdsInsightsCompare(
  objectId: string | null,
  level: AdsLevel,
  since: string,
  until: string,
) {
  return useQuery<AdsInsightsCompare>({
    queryKey: K.compare(objectId ?? "", level, since, until),
    queryFn: () =>
      api.get<AdsInsightsCompare>(
        `/api/meta/ads/insights/compare${qs({
          object_id: objectId,
          level,
          since,
          until,
        })}`,
      ),
    enabled: !!objectId && !!since && !!until,
  });
}

export function useAdsActivities(
  since: string,
  until: string,
  objectId?: string | null,
  eventTypes?: string,
) {
  return useQuery<AdsActivitiesList>({
    queryKey: K.activities(objectId ?? null, since, until),
    queryFn: () =>
      api.get<AdsActivitiesList>(
        `/api/meta/ads/activities${qs({
          object_id: objectId,
          since,
          until,
          event_types: eventTypes,
        })}`,
      ),
    enabled: !!since && !!until,
  });
}

/** Download the per-campaign period report (CSV or PDF). The export
 *  endpoint returns a file, not JSON, so it can't go through the `api`
 *  client — this does an authenticated raw fetch (Bearer from the Supabase
 *  session, same auth the api client uses) and triggers a browser
 *  download. Throws on a non-2xx so callers can toast an error. */
export async function downloadAdsExport(
  format: "csv" | "pdf",
  since: string,
  until: string,
): Promise<void> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token ?? null;
  const url = `${apiBase()}/api/meta/ads/export${qs({ format, since, until })}`;
  const resp = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Falha ao exportar (${resp.status})`);
  const blob = await resp.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = `anuncios_${since}_${until}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

/** Lead-gen (Instant Form) inventory + field schema + volume metrics —
 *  all accessible WITHOUT `leads_retrieval`. `records_available` tells the
 *  UI whether the per-lead records path is unlocked. */
export function useLeadForms() {
  return useQuery<LeadFormsSummary>({
    queryKey: ["meta-ads", "lead-forms"],
    queryFn: () => api.get<LeadFormsSummary>("/api/meta/ads/leads/forms"),
  });
}

/** The per-lead RECORDS for one form — gated on `leads_retrieval`. When
 *  locked the response carries `{gated:true, reason}` (still a 200), so the
 *  UI renders an actionable banner rather than an error. Enabled only when
 *  a form is selected AND records are known to be available. */
export function useLeadRecords(
  formId: string | null,
  pageId: string | null,
  enabled: boolean,
) {
  return useQuery<LeadRecords>({
    queryKey: ["meta-ads", "lead-records", formId ?? "", pageId ?? ""],
    queryFn: () =>
      api.get<LeadRecords>(
        `/api/meta/ads/leads/records${qs({ form_id: formId, page_id: pageId })}`,
      ),
    enabled: enabled && !!formId,
  });
}

/** Trigger a lead ingest (pull forms + records from Meta → upsert to the
 *  DB). Background job — returns a `job_id` to poll via `useSyncJob`. */
export function useLeadSync() {
  return useMutation<AdsSyncStarted, Error, void>({
    mutationFn: () => api.post<AdsSyncStarted>("/api/meta/ads/leads/sync", {}),
  });
}

/** Poll a sync job's status. Auto-refetches every 2s while `running`;
 *  enabled only while a `jobId` is set. Shared by ads + lead syncs (same
 *  `/sync/{job_id}` status endpoint). */
export function useSyncJob(jobId: string | null) {
  return useQuery<AdsSyncStatus>({
    queryKey: ["meta-ads", "sync-job", jobId ?? ""],
    queryFn: () => api.get<AdsSyncStatus>(`/api/meta/ads/sync/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) =>
      q.state.data && q.state.data.status !== "running" ? false : 2000,
  });
}

/** Trigger a sync (incremental by default). Returns the job id; poll
 *  `/sync/{job_id}` separately if you need progress. */
export function useAdsSync() {
  const qc = useQueryClient();
  return useMutation<AdsSyncStarted, Error, "incremental" | "backfill" | undefined>({
    mutationFn: (mode = "incremental") =>
      api.post<AdsSyncStarted>("/api/meta/ads/sync", { mode }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["meta-ads"] });
    },
  });
}
