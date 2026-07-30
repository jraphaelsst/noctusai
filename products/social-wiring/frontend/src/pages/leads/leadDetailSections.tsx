/**
 * THE field list for "one lead, in detail" — declared once, rendered by
 * every surface.
 *
 * This module is the reason "change the modal once and it changes
 * everywhere" is literally true rather than a good intention. Three
 * surfaces open the same `EntityDetailDialog`:
 *
 *   - the Leads table row      (`BaseDeLeads`)
 *   - a Funil de Vendas card   (`NegociacaoCard`)
 *   - a Processos de Venda card (`ProcessoCard`)
 *
 * None of them knows which fields a lead has. They ask here. Adding a
 * field is one edit in this file; before it existed, the Leads drawer had
 * its own hand-written field list and the boards had no detail view at all
 * — they deep-linked back to the table with `?q=<contato>`.
 *
 * TWO ORIGINS, ONE MODAL
 * ----------------------
 * A card is spawned from EITHER a `social_wiring.leads` row OR a
 * `meta_ads_leads` row (migration 034's CHECK guarantees exactly one). A
 * campaign lead is not a `Lead` and has no `/api/leads/{id}` to fetch — it
 * has a form, a campaign and the answers the person typed. So there are
 * two builders, not one builder with a pile of `hidden` flags: the records
 * genuinely differ, and pretending otherwise would render a campaign lead
 * as a lead with fourteen empty fields.
 */
import type { DetailSection } from '@noctusai/lib/components';
import { formatPhone } from '@noctusai/lib/phone';

import type { Lead, LeadSource } from '@/pages/leads/types';
import type { NegociacaoCampanha } from '@/types/pipeline';

const TIPO_LABEL: Record<Lead['tipo_lead'], string> = {
  novo: 'Novo',
  retorno: 'Retorno',
  desconhecido: 'Desconhecido',
};

const TIER_LABEL: Record<NonNullable<Lead['anuncio_tier']>, string> = {
  simples: 'Simples',
  destaque: 'Destaque',
  super_destaque: 'Super destaque',
};

function OrigemChip({ cor, label }: { cor?: string | null; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {cor && <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: cor }} />}
      {label}
    </span>
  );
}

/**
 * Render a contact through the platform's ONE phone seam.
 *
 * Deliberately formats `contato` (what arrived) rather than reading the
 * stored `contato_norm`: `formatPhone` applies the identical rule the DB
 * trigger and the backend primitive apply — the three are one contract,
 * asserted case-for-case in all three runtimes — so the rendered string is
 * the same either way, and this keeps `LeadOut` (§5.3, frozen) unwidened.
 *
 * When a number cannot be canonicalized without guessing, `formatPhone`
 * returns it unchanged instead of blanking it. That is the point: a number
 * a human can see is a number a human can fix.
 */
export function contatoValue(lead: Lead): string | null {
  if (lead.contato_tipo === 'email') return lead.contato?.toLowerCase() ?? null;
  return formatPhone(lead.contato);
}

function dateTimeBR(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('pt-BR');
}

/**
 * `needs_review` alone ("Revisar") tells a non-technical user THAT
 * something is wrong, never WHAT — she cannot fix a flag she cannot
 * interpret. Derive a human reason from what set it (see
 * `dimensions_service.py` / `resolvers.py`): either the origem string from
 * the import sheet matched no known source (`origem_id` is null), or it
 * matched only into the generic "outro" categoria.
 */
export function explainNeedsReview(lead: Lead, sources: LeadSource[] | undefined): string {
  if (!lead.origem_id) {
    return lead.origem_raw
      ? `Origem não reconhecida: "${lead.origem_raw}"`
      : 'Sem origem informada nesta linha';
  }
  const source = sources?.find((s) => s.id === lead.origem_id);
  if (source?.categoria === 'outro') {
    return `Origem mapeada como "Outro" (${source.label}) — revise a categoria em Configuração`;
  }
  return 'Revise os dados deste lead';
}

/** Everything we hold about a lead from the base (`social_wiring.leads`). */
export function leadDetailSections(lead: Lead): DetailSection[] {
  return [
    {
      fields: [
        { label: 'Data de entrada', value: lead.data_entrada },
        { label: 'Tipo', value: TIPO_LABEL[lead.tipo_lead] },
        { label: 'Contato', value: contatoValue(lead) },
        {
          label: 'Origem',
          value: lead.origem ? (
            <OrigemChip cor={lead.origem.cor} label={lead.origem.label} />
          ) : (
            lead.origem_raw
          ),
        },
        { label: 'Corretor', value: lead.corretor?.nome ?? lead.corretor_raw },
        {
          label: 'Tier do anúncio',
          value: lead.anuncio_tier ? TIER_LABEL[lead.anuncio_tier] : null,
        },
        { label: 'Empreendimento', value: lead.empreendimento },
        { label: 'Região', value: lead.regiao },
        { label: 'Código do imóvel', value: lead.codigo_imovel ?? lead.codigo_raw },
        { label: 'Status', value: lead.status },
      ],
    },
    {
      title: 'Follow-up',
      fields: [
        { label: 'Data', value: lead.follow_up_data },
        { label: 'Nota', value: lead.follow_up_nota },
        { label: 'Observações', value: lead.observacoes, wide: true },
      ],
    },
    {
      title: 'Procedência',
      fields: [
        { label: 'Planilha de origem', value: lead.source_sheet },
        { label: 'Linha', value: lead.source_row },
        { label: 'Criado em', value: dateTimeBR(lead.created_at) },
        { label: 'Atualizado em', value: dateTimeBR(lead.updated_at) },
      ],
    },
  ];
}

/**
 * Everything we hold about a lead that came from a Meta campaign.
 *
 * `answers` is the form Q&A the person actually filled in — the most
 * useful thing on the record and, before this modal existed, visible
 * nowhere in the UI at all.
 */
export function campanhaDetailSections(campanha: NegociacaoCampanha): DetailSection[] {
  const answers = campanha.answers ?? {};
  const answerFields = Object.entries(answers).map(([pergunta, resposta]) => ({
    label: pergunta,
    value: Array.isArray(resposta) ? resposta.join(', ') : String(resposta ?? ''),
    wide: true,
  }));

  return [
    {
      fields: [
        { label: 'Nome', value: campanha.full_name },
        { label: 'Telefone', value: formatPhone(campanha.phone) },
        { label: 'Email', value: campanha.email, wide: true },
        { label: 'Recebido em', value: dateTimeBR(campanha.created_time) },
      ],
    },
    {
      title: 'Campanha',
      fields: [
        { label: 'Campanha', value: campanha.campaign_name ?? campanha.campaign_id },
        { label: 'Formulário', value: campanha.form_name ?? campanha.form_id },
        { label: 'Plataforma', value: campanha.platform },
        {
          label: 'Tipo',
          value: campanha.is_organic == null ? null : campanha.is_organic ? 'Orgânico' : 'Pago',
        },
        { label: 'Anúncio', value: campanha.ad_id, hidden: !campanha.ad_id },
        { label: 'Conjunto', value: campanha.adset_id, hidden: !campanha.adset_id },
      ],
    },
    // Dropped entirely when the form had no answers — a "Respostas do
    // formulário" heading over nothing reads as data that failed to load.
    { title: 'Respostas do formulário', fields: answerFields },
  ];
}
