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

/**
 * The campaign lead a Funil card was spawned from (`meta_ads_leads`).
 *
 * Projected WIDER than `NegociacaoLead` on purpose. A lead-origin card can
 * fetch its whole record from `GET /api/leads/{id}` when the detail modal
 * opens; a campaign lead has no such endpoint — there IS no `leads` row for
 * it — so this projection IS the record, and the modal renders straight
 * from it. See `app/modules/pipeline/configs.py`.
 */
export interface NegociacaoCampanha {
  id: string;
  full_name: string | null;
  email: string | null;
  /** Canonical E.164 since migration 037. */
  phone: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  form_id: string | null;
  form_name: string | null;
  ad_id: string | null;
  adset_id: string | null;
  platform: string | null;
  is_organic: boolean | null;
  created_time: string | null;
  /**
   * The form Q&A the person actually filled in, keyed by question text.
   * Values are scalars, or a list when Meta returns a multi-select.
   */
  answers: Record<string, string | string[] | null> | null;
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
  /**
   * The deal this processo came from, carrying the SAME origin joins a Funil
   * card has. Without them a processo card could offer only a title, and
   * "click the card to see the lead" would be true on one board and false on
   * the other.
   */
  negociacao?: {
    id: string;
    titulo: string | null;
    valor_estimado: number | null;
    closed_at: string | null;
    lead_id: string | null;
    meta_ads_lead_id: string | null;
    lead?: NegociacaoLead | null;
    campanha?: NegociacaoCampanha | null;
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

/** Display name for a processo card — the deal it came from. */
export function nomeDoProcesso(p: ProcessoVenda): string {
  const neg = p.negociacao;
  return (
    neg?.titulo ||
    neg?.lead?.cliente_nome ||
    neg?.campanha?.full_name ||
    neg?.lead?.contato ||
    neg?.campanha?.email ||
    neg?.campanha?.phone ||
    "Processo"
  );
}

/**
 * Which record a card's detail modal should show.
 *
 * ONE function, used by both boards, because "what is this card about?" has
 * exactly one answer and two boards asking it differently is how they drift.
 * A card has exactly one origin (migration 034's CHECK), and the two origins
 * are opened differently: a `leads` row is FETCHED whole by id, while a
 * campaign lead has no such endpoint and is rendered from the projection the
 * card already carries.
 */
export interface CardOrigem {
  leadId: string | null;
  campanha: NegociacaoCampanha | null;
}

export function origemDaNegociacao(n: NegociacaoVenda): CardOrigem {
  return { leadId: n.lead_id, campanha: n.campanha ?? null };
}

export function origemDoProcesso(p: ProcessoVenda): CardOrigem {
  const neg = p.negociacao;
  return { leadId: neg?.lead_id ?? null, campanha: neg?.campanha ?? null };
}
