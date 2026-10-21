/**
 * Meta Ads hooks for Orbity — ad accounts, campaigns, campaign metrics,
 * sync seam, and spend-vs-leads aggregate.
 *
 * All list endpoints return { items, total, page, page_size }.
 * Single-resource endpoints return the resource directly.
 * Aggregate returns SpendLeadsAggregate envelope.
 * Sync returns SyncCampaignsResponse.
 *
 * Convention: one file per domain entity, TanStack Query throughout.
 * `api` is imported from `@/lib/api` (the local seam, not seed directly).
 *
 * Nav route keys: "trafego", "contas-de-anuncio"
 * Requires status_pagina rows with those page_key values.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";

// ---------------------------------------------------------------------------
// Domain types (mirrors backend schemas/meta_ads.py)
// ---------------------------------------------------------------------------

export type AdAccountStatus = "active" | "paused" | "disconnected" | "error";
export type CampaignStatus = "active" | "paused" | "archived" | "deleted";
export type SituationLiteral = "on-track" | "attention" | "off";

export interface AdAccount {
  id: string;
  org_id: string;
  client_id: string | null;
  external_account_id: string;
  name: string;
  status: AdAccountStatus;
  connected_at: string;
  created_at: string;
  updated_at: string;
}

export interface Campaign {
  id: string;
  org_id: string;
  client_id: string | null;
  ad_account_id: string;
  external_campaign_id: string;
  name: string;
  objective: string | null;
  status: CampaignStatus;
  daily_budget: number | null;
  result_metric: string | null;
  situation: SituationLiteral;
  created_at: string;
  updated_at: string;
}

export interface CampaignMetric {
  id: string;
  org_id: string;
  campaign_id: string;
  date: string;
  spend: number;
  impressions: number;
  leads: number;
  cpl: number | null;
  created_at: string;
  updated_at: string;
}

export interface ClientMonthAggregate {
  client_id: string | null;
  client_name: string | null;
  month: string;
  total_spend: number;
  total_leads: number;
  avg_cpl: number | null;
  campaign_count: number;
  on_track_count: number;
  attention_count: number;
  off_count: number;
}

export interface SpendLeadsAggregate {
  period_start: string;
  period_end: string;
  items: ClientMonthAggregate[];
  total_spend: number;
  total_leads: number;
}

export interface SyncCampaignsResponse {
  synced: number;
  skipped: number;
  errors: number;
  source: string;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Ad account create / update types
// ---------------------------------------------------------------------------

export interface AdAccountCreate {
  external_account_id: string;
  name: string;
  status?: AdAccountStatus;
  client_id?: string;
  access_token_ref?: string;
}

export interface AdAccountUpdate {
  id: string;
  name?: string;
  status?: AdAccountStatus;
  client_id?: string;
  access_token_ref?: string;
}

export interface AdAccountFilters {
  client_id?: string;
  status?: AdAccountStatus;
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Campaign create / update types
// ---------------------------------------------------------------------------

export interface CampaignCreate {
  ad_account_id: string;
  external_campaign_id: string;
  name: string;
  client_id?: string;
  objective?: string;
  status?: CampaignStatus;
  daily_budget?: number;
  result_metric?: string;
  situation?: SituationLiteral;
}

export interface CampaignUpdate {
  id: string;
  name?: string;
  objective?: string;
  status?: CampaignStatus;
  daily_budget?: number;
  result_metric?: string;
  situation?: SituationLiteral;
}

export interface CampaignFilters {
  ad_account_id?: string;
  client_id?: string;
  situation?: SituationLiteral;
  status?: CampaignStatus;
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Ad accounts
// ---------------------------------------------------------------------------

export function useAdAccounts(filters?: AdAccountFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta-ads-accounts", filters],
    queryFn: async () => {
      return api.get<ListResponse<AdAccount>>("/api/meta-ads/ad-accounts", {
        client_id: filters?.client_id,
        status: filters?.status,
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 50,
      });
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateAdAccount() {
  // Ad accounts are listed newest first (connected_at desc).
  return useCacheWriteMutation<AdAccount, AdAccountCreate>({
    mutationFn: async (data) => {
      return api.post<AdAccount>("/api/meta-ads/ad-accounts", data);
    },
    targets: [
      {
        queryKey: ["meta-ads-accounts", undefined],
        commit: (old: ListResponse<AdAccount> | undefined, saved) => pageOps.prependNewest(old, saved),
      },
      { queryKey: ["meta-ads-accounts"], match: "prefix" },
    ],
    onSuccess: () => {
      toast.success("Conta de anúncio cadastrada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao cadastrar conta de anúncio", {
        description: error.message,
      });
    },
  });
}

export function useUpdateAdAccount() {
  return useCacheWriteMutation<AdAccount, AdAccountUpdate>({
    mutationFn: async ({ id, ...data }) => {
      return api.patch<AdAccount>(`/api/meta-ads/ad-accounts/${id}`, data);
    },
    targets: ({ id }) => [
      {
        queryKey: ["meta-ads-accounts"],
        match: "prefix",
        commit: (old: ListResponse<AdAccount> | undefined, saved) => pageOps.replace(old, id, saved),
      },
    ],
    onSuccess: () => {
      toast.success("Conta de anúncio atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar conta de anúncio", {
        description: error.message,
      });
    },
  });
}

export function useDeleteAdAccount() {
  return useCacheWriteMutation<{ ok: boolean; id: string }, string>({
    mutationFn: async (id) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/meta-ads/ad-accounts/${id}`,
      );
    },
    targets: [
      {
        queryKey: ["meta-ads-accounts"],
        match: "prefix",
        optimistic: (old: ListResponse<AdAccount> | undefined, id) => pageOps.remove(old, id),
      },
    ],
    onSuccess: () => {
      toast.success("Conta de anúncio removida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover conta de anúncio", {
        description: error.message,
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------------------

export function useCampaigns(filters?: CampaignFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta-ads-campaigns", filters],
    queryFn: async () => {
      return api.get<ListResponse<Campaign>>("/api/meta-ads/campaigns", {
        ad_account_id: filters?.ad_account_id,
        client_id: filters?.client_id,
        situation: filters?.situation,
        status: filters?.status,
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 50,
      });
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateCampaign() {
  // Campaigns are listed newest first (created_at desc). The spend/leads aggregate
  // is server-computed, so it only refreshes in the background.
  return useCacheWriteMutation<Campaign, CampaignCreate>({
    mutationFn: async (data) => {
      return api.post<Campaign>("/api/meta-ads/campaigns", data);
    },
    targets: [
      {
        queryKey: ["meta-ads-campaigns", undefined],
        commit: (old: ListResponse<Campaign> | undefined, saved) => pageOps.prependNewest(old, saved),
      },
      { queryKey: ["meta-ads-campaigns"], match: "prefix" },
    ],
    invalidate: [["meta-ads-aggregate"]],
    onSuccess: () => {
      toast.success("Campanha criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar campanha", { description: error.message });
    },
  });
}

export function useUpdateCampaign() {
  return useCacheWriteMutation<Campaign, CampaignUpdate>({
    mutationFn: async ({ id, ...data }) => {
      return api.patch<Campaign>(`/api/meta-ads/campaigns/${id}`, data);
    },
    targets: ({ id }) => [
      {
        queryKey: ["meta-ads-campaigns"],
        match: "prefix",
        commit: (old: ListResponse<Campaign> | undefined, saved) => pageOps.replace(old, id, saved),
      },
    ],
    invalidate: [["meta-ads-aggregate"]],
    onSuccess: () => {
      toast.success("Campanha atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar campanha", { description: error.message });
    },
  });
}

export function useDeleteCampaign() {
  return useCacheWriteMutation<{ ok: boolean; id: string }, string>({
    mutationFn: async (id) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/meta-ads/campaigns/${id}`,
      );
    },
    targets: [
      {
        queryKey: ["meta-ads-campaigns"],
        match: "prefix",
        optimistic: (old: ListResponse<Campaign> | undefined, id) => pageOps.remove(old, id),
      },
    ],
    invalidate: [["meta-ads-aggregate"]],
    onSuccess: () => {
      toast.success("Campanha removida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover campanha", { description: error.message });
    },
  });
}

export function useUpdateSituation() {
  return useCacheWriteMutation<Campaign, { id: string; situation: SituationLiteral }>({
    mutationFn: async ({ id, situation }) => {
      return api.patch<Campaign>(
        `/api/meta-ads/campaigns/${id}/situation`,
        { situation },
      );
    },
    targets: ({ id, situation }) => [
      {
        queryKey: ["meta-ads-campaigns"],
        match: "prefix",
        optimistic: (old: ListResponse<Campaign> | undefined) => pageOps.patch(old, id, { situation }),
        commit: (old: ListResponse<Campaign> | undefined, saved) => pageOps.replace(old, id, saved),
      },
    ],
    onSuccess: () => {
      toast.success("Situação da campanha atualizada!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar situação", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Sync seam (NOC-REMEDIATE[orbity-meta-ads-live])
// ---------------------------------------------------------------------------

export function useSyncCampaigns() {
  const queryClient = useQueryClient();

  return useMutation({ // noc-allow: invalidate-only — the sync pulls campaign/metric changes from Meta server-side and answers with counters only; which rows changed is unknown to the client
    mutationFn: async (adAccountId: string) => {
      return api.post<SyncCampaignsResponse>("/api/meta-ads/sync", {
        ad_account_id: adAccountId,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["meta-ads-metrics"] });
      const sourceLabel = data.source === "live" ? "Meta API" : "dados de teste";
      toast.success(
        `Sincronização concluída (${sourceLabel}): ${data.synced} atualizadas, ${data.skipped} sem mudanças${data.errors ? `, ${data.errors} com erro` : ""}.`,
      );
    },
    onError: (error: Error) => {
      toast.error("Erro ao sincronizar campanhas", {
        description: error.message,
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Aggregate — spend vs leads per client/month
// ---------------------------------------------------------------------------

export function useSpendLeadsAggregate(
  periodStart: string,
  periodEnd: string,
  clientId?: string,
) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta-ads-aggregate", periodStart, periodEnd, clientId],
    queryFn: async () => {
      return api.get<SpendLeadsAggregate>("/api/meta-ads/aggregate", {
        period_start: periodStart,
        period_end: periodEnd,
        client_id: clientId,
      });
    },
    enabled: !!user && !!periodStart && !!periodEnd,
    staleTime: 5 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Campaign metrics — manual daily entry + history
// ---------------------------------------------------------------------------

export interface CampaignMetricUpsertData {
  date: string; // YYYY-MM-DD
  spend: number;
  impressions: number;
  leads: number;
  cpl?: number;
}

/** GET /api/meta-ads/campaigns/{id}/metrics -> plain list, newest first. */
export function useCampaignMetrics(campaignId: string | null) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta-ads-metrics", campaignId],
    queryFn: async () => {
      return api.get<CampaignMetric[]>(
        `/api/meta-ads/campaigns/${campaignId}/metrics`,
      );
    },
    placeholderData: (prev) => prev,
    enabled: !!user && !!campaignId,
    staleTime: 60 * 1000,
  });
}

/**
 * PUT /api/meta-ads/campaigns/{id}/metrics — manual daily metric entry
 * (campaign_id + date is the upsert key). Body mirrors campaign_metrics
 * (migration 009) minus campaign_id, which the path carries.
 */
export function useUpsertCampaignMetric(campaignId: string) {
  // Metrics are listed newest first (date desc): the saved day replaces its row (or
  // is inserted at its date). The spend/leads aggregate is server-computed.
  return useCacheWriteMutation<CampaignMetric, CampaignMetricUpsertData>({
    mutationFn: async (data) => {
      return api.put<CampaignMetric>(
        `/api/meta-ads/campaigns/${campaignId}/metrics`,
        data,
      );
    },
    targets: [
      {
        queryKey: ["meta-ads-metrics", campaignId],
        commit: (old: CampaignMetric[] | undefined, saved) =>
          listOps.replace(old, saved.id, saved)?.sort((a, b) => b.date.localeCompare(a.date)),
      },
    ],
    invalidate: [["meta-ads-aggregate"]],
    onSuccess: () => {
      toast.success("Métricas salvas");
    },
    onError: (error: Error) => {
      toast.error("Erro ao salvar métricas", { description: error.message });
    },
  });
}
