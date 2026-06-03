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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: AdAccountCreate) => {
      return api.post<AdAccount>("/api/meta-ads/ad-accounts", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-accounts"] });
      toast.success("Conta de anúncio conectada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao conectar conta de anúncio", {
        description: error.message,
      });
    },
  });
}

export function useUpdateAdAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: AdAccountUpdate) => {
      return api.patch<AdAccount>(`/api/meta-ads/ad-accounts/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-accounts"] });
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/meta-ads/ad-accounts/${id}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-accounts"] });
      toast.success("Conta de anúncio desconectada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao desconectar conta de anúncio", {
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
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CampaignCreate) => {
      return api.post<Campaign>("/api/meta-ads/campaigns", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["meta-ads-aggregate"] });
      toast.success("Campanha criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar campanha", { description: error.message });
    },
  });
}

export function useUpdateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: CampaignUpdate) => {
      return api.patch<Campaign>(`/api/meta-ads/campaigns/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["meta-ads-aggregate"] });
      toast.success("Campanha atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar campanha", { description: error.message });
    },
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/meta-ads/campaigns/${id}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["meta-ads-aggregate"] });
      toast.success("Campanha removida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover campanha", { description: error.message });
    },
  });
}

export function useUpdateSituation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      id,
      situation,
    }: {
      id: string;
      situation: SituationLiteral;
    }) => {
      return api.patch<Campaign>(
        `/api/meta-ads/campaigns/${id}/situation`,
        { situation },
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-ads-campaigns"] });
      toast.success("Situação da campanha atualizada!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar situação", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Campaign metrics
// ---------------------------------------------------------------------------

export function useCampaignMetrics(
  campaignId: string,
  dateFrom?: string,
  dateTo?: string,
) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta-ads-metrics", campaignId, dateFrom, dateTo],
    queryFn: async () => {
      return api.get<CampaignMetric[]>(
        `/api/meta-ads/campaigns/${campaignId}/metrics`,
        {
          date_from: dateFrom,
          date_to: dateTo,
        },
      );
    },
    enabled: !!user && !!campaignId,
    staleTime: 2 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Sync seam (NOC-REMEDIATE[orbity-meta-ads-live])
// ---------------------------------------------------------------------------

export function useSyncCampaigns() {
  const queryClient = useQueryClient();

  return useMutation({
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
