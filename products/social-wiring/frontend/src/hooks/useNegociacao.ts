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

// ─── Keys ───────────────────────────────────────────────────────────────────

const NEGOCIACAO_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "negociacao"] as const;
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
