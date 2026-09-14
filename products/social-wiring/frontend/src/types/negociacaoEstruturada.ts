/**
 * Negociação estruturada — the itemised deal terms a contract is drafted
 * from: parcelas, quem recebe cada uma, intermediários, posse and permuta.
 *
 * 🔴 EVERY MONEY VALUE IS A STRING, END TO END.
 * Same rule as `@/hooks/useNegociacao` — the backend computes and serialises
 * in `Decimal` so the parts add up to the whole. Parsing these to `Number`
 * for anything but display would reintroduce the float error the backend
 * went to trouble to avoid, and the place it would surface is a payout.
 *
 * 🔴 NULLABILITY — every `*_at` and optional field is nullable.
 * F0 lesson: a fresh row returned `updated_at: null` while the FE typed it
 * `string`. Every timestamp here is `string | null`.
 */

export type ParcelaTipo =
  | "sinal"
  | "intermediaria"
  | "financiamento"
  | "fgts"
  | "saldo"
  | "direta";

export interface NegociacaoParcela {
  id: string;
  tipo: ParcelaTipo;
  /** BRL as a decimal string, e.g. "6750.00". Never parsed to float. */
  valor: string;
  vencimento: string | null;
  evento: string | null;
  forma_pagamento: string | null;
  favorecido_id: string | null;
  confissao_divida: boolean;
  ordem: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface NegociacaoFavorecido {
  id: string;
  nome: string;
  cpf_cnpj: string | null;
  banco: string | null;
  agencia: string | null;
  conta: string | null;
  pix: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type IntermediarioTipo = "percentual" | "valor_fixo";

export interface NegociacaoIntermediario {
  id: string;
  corretor_id: string | null;
  nome: string;
  creci: string | null;
  tipo: IntermediarioTipo;
  /** Percentage (0-100) as a string when `tipo === "percentual"`, BRL
   *  decimal string when `tipo === "valor_fixo"`. Never parsed to float. */
  valor: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface NegociacaoCompletude {
  completo: boolean;
  faltando: string[];
}

export interface NegociacaoEstruturada {
  atendimento_id: string;
  valor_negociado: string | null;
  saldo_nao_alocado: string | null;
  posse_data: string | null;
  posse_condicoes: string | null;
  permuta_ativo_id: string | null;
  parcelas: NegociacaoParcela[];
  favorecidos: NegociacaoFavorecido[];
  intermediarios: NegociacaoIntermediario[];
  completude: NegociacaoCompletude;
}

// ─── Write payloads ─────────────────────────────────────────────────────────

export interface ParcelaCreate {
  tipo: ParcelaTipo;
  valor: string;
  vencimento?: string | null;
  evento?: string | null;
  forma_pagamento?: string | null;
  favorecido_id?: string | null;
  confissao_divida?: boolean;
  ordem?: number;
}

export type ParcelaPatch = Partial<ParcelaCreate>;

export interface DividirSaldoPayload {
  /** 1-360. */
  num_parcelas: number;
  /** Defaults server-side to "direta". */
  tipo?: ParcelaTipo;
  forma_pagamento?: string | null;
  favorecido_id?: string | null;
  vencimento_inicial?: string | null;
}

export interface FavorecidoCreate {
  nome: string;
  cpf_cnpj?: string | null;
  banco?: string | null;
  agencia?: string | null;
  conta?: string | null;
  pix?: string | null;
}

export type FavorecidoPatch = Partial<FavorecidoCreate>;

export interface IntermediarioCreate {
  corretor_id?: string | null;
  nome: string;
  creci?: string | null;
  /** Defaults server-side to "percentual". */
  tipo?: IntermediarioTipo;
  valor?: string | null;
}

export type IntermediarioPatch = Partial<IntermediarioCreate>;

/** The subset of the existing `.../negociacao` PATCH this panel writes to —
 *  posse and permuta only. See `useNegociacaoPosseMutation`. */
export interface NegociacaoPossePatch {
  posse_data?: string | null;
  posse_condicoes?: string | null;
  permuta_ativo_id?: string | null;
}

export const PARCELA_TIPO_LABELS: Record<ParcelaTipo, string> = {
  sinal: "Sinal",
  intermediaria: "Intermediária",
  financiamento: "Financiamento",
  fgts: "FGTS",
  saldo: "Saldo",
  direta: "Direta",
};

export const INTERMEDIARIO_TIPO_LABELS: Record<IntermediarioTipo, string> = {
  percentual: "Percentual",
  valor_fixo: "Valor fixo",
};
