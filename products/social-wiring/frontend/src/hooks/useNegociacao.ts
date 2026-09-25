/**
 * Negociação — the commercial terms of a deal, and the computed split.
 *
 * 🔴 EVERY MONEY VALUE IS A STRING, END TO END.
 * The backend computes the split in `Decimal` and serialises to strings for a
 * reason: `JSON.parse` turns a number into an IEEE double, and 0.1 + 0.2 is
 * not 0.3 there either. Parsing these to `Number` for anything but display
 * would reintroduce exactly the error the backend went to trouble to avoid,
 * and the place it would surface is a commission payout.
 *
 * So they stay strings, and formatting for display is the only thing done to
 * them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { ImovelVisita } from "@/types/cardHub";
import { invalidateExtracaoDependentes } from "@/hooks/useCardHub";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface AgenteSlice {
  id: string;
  nome: string;
  /** BRL as a decimal string, e.g. "6750.00". */
  valor: string;
}

export interface NegociacaoCalculo {
  /** False when there is not yet enough to compute — NOT an error state. */
  calculavel: boolean;
  /** Why it cannot be computed, in words, when `calculavel` is false. */
  motivo: string | null;
  comissao_total: string | null;
  parceria: string | null;
  nossa_parte: string | null;
  agencia: string | null;
  agentes_total: string | null;
  agentes: AgenteSlice[];
  captador_total: string | null;
  captador: { id: string; nome: string | null } | null;
}

export interface Negociacao {
  atendimento_id: string;
  /** 🔴 THE DEAL — the property actually being sold. Set by a human, or by
   *  accepting a proposta on a visita. NEVER derived from `lead_imovel`. */
  imovel_codigo: string | null;
  valor_negociado: string | null;
  pct_comissao: string | null;
  tem_parceria: boolean;
  pct_parceria: string;
  pct_agencia: string;
  pct_agentes: string;
  pct_captador: string;
  formas_pagamento: string | null;
  parcelas: string | null;
  financiamento: boolean;
  fgts: boolean;
  observacoes: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** False when no terms have been recorded yet — the row is the org defaults. */
  existe: boolean;
  calculo: NegociacaoCalculo;

  /** 🔴 THE ORIGIN — the anúncio the LEAD came from (`leads.codigo_imovel`),
   *  enriched through the same path the picker uses. A SIBLING of
   *  `imovel_codigo`, never a fallback for it.
   *
   *  The owner: a portal lead always names the listing the person enquired
   *  about, and "not necessarily that ref is the one that will have the
   *  proposta". It often IS the same property — which is why the UI offers it
   *  as a one-click shortcut — but offering and deciding are different acts,
   *  and only a person may do the second.
   *
   *  `null` for a manually-created card and for a lead with no código: the UI
   *  renders nothing there rather than an empty affordance. */
  lead_imovel: ImovelVisita | null;
}

export interface NegociacaoPatch {
  imovel_codigo?: string | null;
  valor_negociado?: string | null;
  pct_comissao?: string | null;
  tem_parceria?: boolean;
  pct_parceria?: string;
  pct_agencia?: string;
  pct_agentes?: string;
  pct_captador?: string;
  formas_pagamento?: string | null;
  parcelas?: string | null;
  financiamento?: boolean;
  fgts?: boolean;
  observacoes?: string | null;
}

export interface NegociacaoDefaults {
  pct_comissao: string | null;
  pct_parceria: string;
  pct_agencia: string;
  pct_agentes: string;
  pct_captador: string;
}

// ─── Negociação/financiamento extraction conflicts (migration 171,
//     `sw-negociacao-extracao-contract.md` §C.6/§E.5) ──────────────────────
//
// The fourth `campo_conflitos` descriptor (`atendimento_campo_conflitos`,
// keyed by `atendimento_id`) — the deal-scoped sibling of `useCardHub
// .ConflitoCampo` (cliente-scoped). Opened whenever a document disagrees
// with the current value, or with an EARLIER document (H2: no source is
// authoritative), never resolved by overwriting.

export type NegociacaoConflitoStatus = "pendente" | "aceito" | "rejeitado";

/** `campo` vocabulary per the contract: `"valor_negociado"` ·
 *  `"parcela.<id>.valor"` · `"financiamento.fgts"` ·
 *  `"financiamento.numero_proposta"` · `"financiamento.agente_financeiro_id"`.
 *  Kept as a plain string (not a union) — a new campo the FE doesn't
 *  recognise yet must still render, not vanish. */
export interface NegociacaoConflito {
  id: string;
  atendimento_id: string;
  campo: string;
  valor_anterior: string | null;
  origem_anterior: string | null;
  valor_proposto: string;
  origem_proposto: string;
  documento_id_proposto: string | null;
  status: NegociacaoConflitoStatus;
  created_at: string;
}

/** pt-BR for a `campo` value — falls back to the raw key, same
 *  never-blank posture `rotuloNegociacaoFaltando` uses. */
const CONFLITO_CAMPO_LABEL: Record<string, string> = {
  valor_negociado: "Valor negociado",
  "financiamento.fgts": "Uso de FGTS",
  "financiamento.numero_proposta": "Número da proposta",
  "financiamento.agente_financeiro_id": "Agente financeiro",
};

export function rotuloConflitoCampo(campo: string): string {
  if (campo.startsWith("parcela.")) return "Valor da parcela";
  return CONFLITO_CAMPO_LABEL[campo] ?? campo;
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const NEGOCIACAO_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "negociacao"] as const;
const CONFLITOS_KEY = (clienteId: string) =>
  [...NEGOCIACAO_KEY(clienteId), "conflitos"] as const;
const DEFAULTS_KEY = ["sw", "negociacao", "defaults"] as const;

const base = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/negociacao`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useNegociacao(clienteId: string | null) {
  return useQuery({
    queryKey: NEGOCIACAO_KEY(clienteId ?? "__none__"),
    queryFn: async () => api.get<Negociacao>(base(clienteId as string)),
    enabled: !!clienteId,
  });
}

export function useNegociacaoDefaults() {
  return useQuery({
    queryKey: DEFAULTS_KEY,
    queryFn: async () =>
      api.get<NegociacaoDefaults>("/api/negociacao/defaults"),
  });
}

/** `GET /api/clientes/{cliente_id}/negociacao/conflitos` (contract §E.5) —
 *  every pending-or-decided conflict for THIS deal. The panel filters to
 *  `status === "pendente"` for the banner; the full history stays fetchable
 *  for anyone who needs to see what a past decision was. */
export function useNegociacaoConflitos(clienteId: string | null) {
  return useQuery({
    queryKey: CONFLITOS_KEY(clienteId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ items: NegociacaoConflito[] }>(
        `${base(clienteId as string)}/conflitos`,
      );
      return res?.items ?? [];
    },
    enabled: !!clienteId,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export function useNegociacaoMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: NegociacaoPatch) =>
      api.patch<Negociacao>(base(clienteId), patch),
    onSuccess: (data) => {
      // The PATCH returns the full row WITH a freshly computed split, so
      // seeding beats invalidating: the numbers on screen are the ones the
      // server just calculated, not a second read that could disagree.
      qc.setQueryData(NEGOCIACAO_KEY(clienteId), data);
      // Bug 2 (prod card 755253934) — Salvar changes `imovel_codigo`/deal
      // terms that "Qualificação para contrato" and geração-readiness read
      // alongside negociação itself; without this they kept the
      // pre-Salvar snapshot until reload, same class as the extraction
      // staleness `useExtracaoPollingInvalidation` (`useCardHub.ts`) fixes.
      void invalidateExtracaoDependentes(qc, clienteId);
    },
  });
}

/** `POST /api/clientes/{cliente_id}/negociacao/conflitos/{id}/resolver
 *  {decisao}` (contract §E.5). Field name (`decisao`) is pinned by the
 *  contract; the value vocabulary is NOT — `"aceitar"`/`"rejeitar"` picked
 *  as the obvious binary, mirroring this product's existing
 *  Aprovar/Rejeitar wording (`ConflitosPendentesCard`). Flag for
 *  reconciliation with S2 if the backend lands a different pair. */
export type NegociacaoConflitoDecisao = "aceitar" | "rejeitar";

export function useResolverNegociacaoConflito(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      conflitoId,
      decisao,
    }: {
      conflitoId: string;
      decisao: NegociacaoConflitoDecisao;
    }) =>
      api.post<NegociacaoConflito>(
        `${base(clienteId)}/conflitos/${encodeURIComponent(conflitoId)}/resolver`,
        { decisao },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CONFLITOS_KEY(clienteId) });
      // Accepting a conflict writes the real field — the same surfaces a
      // normal negociação/parcela save touches.
      void qc.invalidateQueries({ queryKey: NEGOCIACAO_KEY(clienteId) });
      void qc.invalidateQueries({
        queryKey: ["sw", "clientes", clienteId, "negociacao", "estruturada"],
      });
      void invalidateExtracaoDependentes(qc, clienteId);
    },
  });
}

export function useNegociacaoDefaultsMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<NegociacaoDefaults>) =>
      api.patch<NegociacaoDefaults>("/api/negociacao/defaults", patch),
    onSuccess: (data) => {
      qc.setQueryData(DEFAULTS_KEY, data);
      // 🔴 Existing negociações are deliberately NOT invalidated. Their
      // percentages were copied at creation and the new rule does not apply
      // to them — refetching would suggest it might.
    },
  });
}

// ─── Display helpers ────────────────────────────────────────────────────────

/** Format a decimal STRING as BRL. Never takes a number — see the file header. */
export function formatBRL(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Format a percentage string, trimming the trailing zeros SQL hands back. */
export function formatPct(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toLocaleString("pt-BR", { maximumFractionDigits: 3 })}%`;
}
