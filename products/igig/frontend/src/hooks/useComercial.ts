/**
 * CRM, orçamentos e contratos — Módulo 1.
 *
 * Backend mirror: `app/routers/comercial_router.py`.
 *
 * `useEstimar` is a MUTATION rather than a query even though it only reads:
 * it is an explicit "price this scope" action driven by a form, and caching it
 * by scope would surface a stale price after someone edits the team's rates.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type FormatoEscopo = "feed" | "carrossel" | "story" | "reels" | "video" | "artigo";
export const FORMATOS_ESCOPO: FormatoEscopo[] =
  ["feed", "carrossel", "story", "reels", "video", "artigo"];

export interface Lead {
  id: string;
  nome: string;
  email: string | null;
  telefone: string | null;
  empresa: string | null;
  nicho: string | null;
  dores: string | null;
  orcamento_disponivel: number | null;
  status: "novo" | "qualificado" | "descartado" | "convertido";
  cliente_id: string | null;
}

export interface ItemEscopo {
  formato: FormatoEscopo;
  quantidade: number;
  horas_unitarias?: number;
}

export interface Estimativa {
  horas: number;
  custo: number;
  preco_sugerido: number;
  custo_hora_medio: number;
  margem_alvo: number;
  /** Non-empty ⇒ the suggestion is unreliable. Must be shown before quoting. */
  alertas: string[];
}

export interface Orcamento {
  id: string;
  titulo: string;
  escopo: ItemEscopo[];
  horas_estimadas: number;
  custo_estimado: number;
  preco_sugerido: number;
  preco_final: number | null;
  margem_alvo: number;
  status: string;
}

export interface ContratoDocumento {
  contrato_id: string;
  documento_key: string;
  provedor: string;
  link_assinatura: string;
  external_id: string;
  /** True ⇒ no signing vendor was contacted. Must be surfaced. */
  dry_run: boolean;
}

export const COMERCIAL_QUERY_KEY = ["igig", "comercial"] as const;

export function useLeads(status?: string) {
  const query = useQuery({
    queryKey: [...COMERCIAL_QUERY_KEY, "leads", status ?? ""],
    queryFn: () => api.get<Lead[]>("/api/comercial/leads", status ? { status_filtro: status } : {}),
    // `status` rides in the key — switching the filter is a new key. Keep
    // the previous list on screen instead of blanking to a skeleton.
    placeholderData: (prev) => prev,
  });
  return { ...query, leads: query.data ?? [], loading: query.isPending && !query.data };
}

export function useConverterLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) => api.post<Lead>(`/api/comercial/leads/${leadId}/converter`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COMERCIAL_QUERY_KEY });
      // A converted lead becomes a cliente — that list is now stale too.
      qc.invalidateQueries({ queryKey: ["igig", "clientes"] });
    },
  });
}

export function useEstimar() {
  return useMutation({
    mutationFn: ({ itens, margem_alvo }: { itens: ItemEscopo[]; margem_alvo: number }) =>
      api.post<Estimativa>(`/api/comercial/estimar?margem_alvo=${margem_alvo}`, itens),
  });
}

export function useOrcamentos() {
  const query = useQuery({
    queryKey: [...COMERCIAL_QUERY_KEY, "orcamentos"],
    queryFn: () => api.get<Orcamento[]>("/api/comercial/orcamentos"),
  });
  return { ...query, orcamentos: query.data ?? [], loading: query.isPending && !query.data };
}

export function useCriarOrcamento() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      titulo: string; itens: ItemEscopo[]; margem_alvo: number;
      lead_id?: string; cliente_id?: string;
    }) => api.post<Orcamento>("/api/comercial/orcamentos", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: COMERCIAL_QUERY_KEY }),
  });
}

export function useDefinirPrecoFinal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, preco_final }: { id: string; preco_final: number }) =>
      api.post<Orcamento>(`/api/comercial/orcamentos/${id}/preco`, { preco_final }),
    onSuccess: () => qc.invalidateQueries({ queryKey: COMERCIAL_QUERY_KEY }),
  });
}

export function useGerarContrato() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      cliente_id: string; valor_mensal: number; titulo?: string;
      posts_por_mes?: number; vigencia?: string; clausulas?: string[];
      orcamento_id?: string;
    }) => api.post<ContratoDocumento>("/api/comercial/contratos/gerar", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: COMERCIAL_QUERY_KEY }),
  });
}
