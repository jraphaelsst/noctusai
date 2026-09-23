/**
 * Fontes de lead — WhatsApp (WAHA) and Meta Lead Ads setup (wave-2 contract,
 * Slice E2). Backend mirror: `app/routers/integracoes_leads_router.py`.
 *
 *   GET/PUT /api/integracoes/leads/whatsapp   {base_url, api_key?, session}
 *   GET/PUT /api/integracoes/leads/meta       {page_id, verify_token?, page_access_token?, app_secret?}
 *
 * PUT is org-admin only (403 `admin_obrigatorio` otherwise). No answer ever
 * carries a secret — only `*_configurad[oa]` booleans; a secret omitted on
 * PUT keeps the stored one. Envelope `{data}`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, cleanParams, unwrapData } from "@/lib/api";

export interface WhatsappLeadsStatus {
  configurado: boolean;
  base_url: string | null;
  session: string;
  api_key_configurada: boolean;
  /** Paste this into WAHA's webhook config. Null until first save. */
  webhook_url: string | null;
  /** Why `webhook_url` could not be built (PRODUCT_URL_IGIG missing). */
  webhook_url_erro: string | null;
  hmac_configurado: boolean;
  cofre_configurado: boolean;
  conectado_em: string | null;
  ultimo_erro: string | null;
}

export interface WhatsappLeadsInput {
  base_url: string;
  api_key?: string;
  session: string;
}

export type OrigemAppSecret = "org" | "plataforma" | "nenhuma";

export interface MetaLeadsStatus {
  configurado: boolean;
  page_id: string | null;
  verify_token_configurado: boolean;
  page_access_token_configurado: boolean;
  app_secret_configurado: boolean;
  app_secret_origem: OrigemAppSecret;
  webhook_url: string | null;
  webhook_url_erro: string | null;
  cofre_configurado: boolean;
  conectado_em: string | null;
  ultimo_erro: string | null;
}

export interface MetaLeadsInput {
  page_id: string;
  verify_token?: string;
  page_access_token?: string;
  app_secret?: string;
}

export const LEAD_SOURCES_KEY = ["igig", "integracoes", "leads"] as const;
const WHATSAPP_KEY = [...LEAD_SOURCES_KEY, "whatsapp"] as const;
const META_KEY = [...LEAD_SOURCES_KEY, "meta"] as const;

export function useWhatsappLeads() {
  const query = useQuery({
    queryKey: WHATSAPP_KEY,
    queryFn: () => api.get("/api/integracoes/leads/whatsapp").then(unwrapData<WhatsappLeadsStatus>),
  });
  const data = query.data;
  return { ...query, status: data ?? null, showSkeleton: query.isPending && !data, isRefreshing: query.isFetching && !!data };
}

export function useSalvarWhatsappLeads() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: WhatsappLeadsInput) =>
      api.put("/api/integracoes/leads/whatsapp", cleanParams({ ...payload })).then(unwrapData<WhatsappLeadsStatus>),
    onSuccess: (status) => qc.setQueryData(WHATSAPP_KEY, status),
  });
}

export function useMetaLeads() {
  const query = useQuery({
    queryKey: META_KEY,
    queryFn: () => api.get("/api/integracoes/leads/meta").then(unwrapData<MetaLeadsStatus>),
  });
  const data = query.data;
  return { ...query, status: data ?? null, showSkeleton: query.isPending && !data, isRefreshing: query.isFetching && !!data };
}

export function useSalvarMetaLeads() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: MetaLeadsInput) =>
      api.put("/api/integracoes/leads/meta", cleanParams({ ...payload })).then(unwrapData<MetaLeadsStatus>),
    onSuccess: (status) => qc.setQueryData(META_KEY, status),
  });
}
