import type { PipelineStage } from "@noctusai/lib/components";

/** The lead a Funil card was spawned from (`social_wiring.leads`). */
export interface NegociacaoLead {
  id: string;
  cliente_nome: string | null;
  contato: string | null;
  contato_tipo: string | null;
  empreendimento: string | null;
  regiao: string | null;
  data_entrada: string | null;
  origem_raw: string | null;
}

/** The campaign lead a Funil card was spawned from (`meta_ads_leads`). */
export interface NegociacaoCampanha {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  campaign_id: string | null;
  form_id: string | null;
  created_time: string | null;
}

/**
 * A Funil card. Exactly ONE of `lead` / `campanha` is present — the DB CHECK
 * in migration 034 enforces it, so the UI can branch on presence without a
 * discriminator field that could disagree with the FKs.
 */
export interface NegociacaoVenda {
  id: string;
  org_id: string;
  lead_id: string | null;
  meta_ads_lead_id: string | null;
  etapa_id: string;
  etapa_rel?: PipelineStage | null;
  status: "aberta" | "aceita" | "perdida";
  titulo: string | null;
  valor_estimado: number;
  kanban_pos: number;
  arquivado: boolean;
  closed_at: string | null;
  created_at: string;
  lead?: NegociacaoLead | null;
  campanha?: NegociacaoCampanha | null;
}

export interface ProcessoVenda {
  id: string;
  org_id: string;
  negociacao_venda_id: string;
  etapa_id: string;
  etapa_rel?: PipelineStage | null;
  valor: number;
  observacoes: string | null;
  kanban_pos: number;
  arquivado: boolean;
  created_at: string;
  negociacao?: {
    id: string;
    titulo: string | null;
    valor_estimado: number | null;
    closed_at: string | null;
    lead_id: string | null;
    meta_ads_lead_id: string | null;
  } | null;
}

/** Display name for a card, whichever origin it has. */
export function nomeDaNegociacao(n: NegociacaoVenda): string {
  return (
    n.titulo ||
    n.lead?.cliente_nome ||
    n.campanha?.full_name ||
    n.lead?.contato ||
    n.campanha?.email ||
    n.campanha?.phone ||
    "Lead sem nome"
  );
}

/** The contact string a card should show + deep-link the Leads page by. */
export function contatoDaNegociacao(n: NegociacaoVenda): string | null {
  return n.lead?.contato ?? n.campanha?.phone ?? n.campanha?.email ?? null;
}

/**
 * Deep link into the Leads page, filtered to this card's lead.
 *
 * `?q=` is the Leads module's canonical shared search param (see
 * `hooks/useLeadsFilters.ts`) — the sticky filter bar reads it and EVERY
 * subtab re-scopes off it, so this lands the user on the real Leads surface
 * rather than a bespoke detail route the module does not have.
 */
export function linkParaLeads(n: NegociacaoVenda): string {
  const termo = contatoDaNegociacao(n) ?? nomeDaNegociacao(n);
  return `/leads?q=${encodeURIComponent(termo)}`;
}
