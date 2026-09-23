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
  /** LEGACY (114): the office folded FGTS into the `financiamento` parcela —
   *  `contrato_gerador` now BLOCKS generation on a separate `fgts` parcela
   *  (`PARCELA_FGTS_SEPARADA`). Still a valid `tipo` the backend accepts (old
   *  rows exist), just no longer offered on create — see `PARCELA_TIPOS_CRIAVEIS`. */
  | "fgts"
  | "saldo"
  | "direta"
  /** A payment made by handing over a `permuta_ativos` (natureza
   *  `permuta_imovel`) instead of money — see `permuta_ativo_ids`. */
  | "permuta";

/** Selectable on a NEW parcela — `fgts` excluded (see `ParcelaTipo`). An
 *  existing `fgts` row keeps rendering (with a warning), it is just not an
 *  option going forward. */
export const PARCELA_TIPOS_CRIAVEIS: ParcelaTipo[] = [
  "sinal",
  "intermediaria",
  "financiamento",
  "saldo",
  "direta",
  "permuta",
];

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
  /** Migration 114. Paying this parcela triggers the brokerage payment. */
  dispara_corretagem: boolean;
  /** Migration 114. `tipo === "permuta"` only — the `permuta_ativos`
   *  (natureza `permuta_imovel`) this parcela is paid with. */
  permuta_ativo_ids: string[];
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

/**
 * Migration 162. `"intermediario"` (default): a contracted party the
 * generated contract's commission-clause header QUALIFIES (CRECI required)
 * — the only meaning this table had before 162. `"parceiro_split"`: a
 * commission-split beneficiary that is never qualified in the header and
 * never requires a CRECI (a company or person sharing a cut of the
 * commission, not a licensed broker) — matches reference contract 08's own
 * shape, where a 3rd beneficiary appears only in the split-payment
 * paragraph, never in "as empresas a seguir qualificadas".
 */
export type IntermediarioNatureza = "intermediario" | "parceiro_split";

export const INTERMEDIARIO_NATUREZA_LABELS: Record<IntermediarioNatureza, string> = {
  intermediario: "Corretor / intermediário (com CRECI)",
  parceiro_split: "Parceiro sem CRECI (recebe parte da comissão)",
};

export type PessoaTipo = "pf" | "pj";

/** Migration 114 — PF/PJ qualification shared by create/patch/read. Every
 *  field nullable: an intermediário may be registered with only nome/CRECI
 *  for a long time before the qualification is filled in. */
export interface IntermediarioQualificacao {
  favorecido_id: string | null;
  pessoa_tipo: PessoaTipo | null;
  documento: string | null;
  email: string | null;
  endereco_cep: string | null;
  endereco_logradouro: string | null;
  endereco_numero: string | null;
  endereco_complemento: string | null;
  endereco_bairro: string | null;
  endereco_cidade: string | null;
  endereco_uf: string | null;
  representante_nome: string | null;
  representante_cpf: string | null;
}

export interface NegociacaoIntermediario extends IntermediarioQualificacao {
  id: string;
  corretor_id: string | null;
  nome: string;
  creci: string | null;
  tipo: IntermediarioTipo;
  /** Percentage (0-100) as a string when `tipo === "percentual"`, BRL
   *  decimal string when `tipo === "valor_fixo"`. Never parsed to float. */
  valor: string | null;
  /** Migration 162 — see `IntermediarioNatureza`. */
  natureza: IntermediarioNatureza;
  /** Free-text CRM metadata (why a 'parceiro_split' shares the commission)
   *  — never rendered into the generated contract. */
  papel: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface NegociacaoCompletude {
  completo: boolean;
  faltando: string[];
}

/**
 * Every key `negociacao_estruturada_service._completude`'s `faltando` can
 * name (backend `negociacao_estruturada_service.py::_completude`) — same
 * label-map-with-fallback treatment `qualificacaoCompletude.ts`'s
 * `FALTANDO_LABELS`/`rotuloFaltando` already established for the (unrelated)
 * qualificação-civil completude, so a raw backend key never reaches the
 * operator as literal text.
 */
export const NEGOCIACAO_FALTANDO_LABELS: Record<string, string> = {
  valor_negociado: "Valor negociado não informado",
  parcelas: "Nenhuma parcela cadastrada",
  parcelas_nao_cobrem_valor_negociado: "As parcelas não cobrem o valor negociado",
  posse: "Termos de posse não preenchidos",
  parcela_permuta_sem_imoveis: "Parcela de permuta sem imóveis de permuta vinculados",
};

/** pt-BR label for one `faltando` entry, falling back to the raw key so an
 *  unrecognised (future) key is still visible rather than silently dropped. */
export function rotuloNegociacaoFaltando(chave: string): string {
  return NEGOCIACAO_FALTANDO_LABELS[chave] ?? chave;
}

// ─── Termos do negócio (migration 114) — the contract clauses no document
// carries. `TermosNegocioPutBody` on the backend: PUT replaces this WHOLE
// object, an absent key is stored as null — every field here is nullable and
// a write always sends the complete shape. ─────────────────────────────────

export type PosseMarco = "assinatura" | "parcela" | "protocolo_registro";

export type OnusQuitacao =
  | "compradores_prazo"
  | "interveniente_quitante"
  | "parcela"
  | "ja_quitado";

export type CorretagemContratantes = "vendedores" | "compradores" | "partes";

export interface NegociacaoTermos {
  posse_prazo_dias: number | null;
  posse_marco: PosseMarco | null;
  posse_marco_parcela_id: string | null;

  permuta_posse_prazo_dias: number | null;
  permuta_posse_marco: PosseMarco | null;
  permuta_posse_marco_parcela_id: string | null;
  permuta_obrigacoes_entrega: string | null;

  itens_integrantes: string | null;
  /** Migration 163 — `true` = a human confirmed this deal has NO itens
   *  integrantes. With `itens_integrantes` null and this `false`, the
   *  question is UNANSWERED and contract generation blocks. */
  itens_integrantes_ausente_confirmado: boolean;
  /** `null` = unanswered (blocks generation); `false` is a real "não". */
  ad_corpus: boolean | null;
  obrigacoes_vendedor: string | null;

  onus_quitacao: OnusQuitacao | null;
  onus_prazo_dias: number | null;

  /** % ao mês, e.g. "1.5". Never parsed to float. */
  confissao_juros_am: string | null;
  confissao_garantia: string | null;

  corretagem_contratantes: CorretagemContratantes | null;
  corretagem_num_parcelas: number | null;
}

/** PUT body — same shape as `NegociacaoTermos` minus the read-only parts
 *  (there are none; every field here IS the write surface). Kept as a
 *  distinct alias so a future read-only addition to `NegociacaoTermos` does
 *  not silently widen what a PUT is allowed to send. */
export type TermosNegocioPut = NegociacaoTermos;

export const POSSE_MARCOS: PosseMarco[] = ["assinatura", "parcela", "protocolo_registro"];
export const ONUS_QUITACOES: OnusQuitacao[] = [
  "compradores_prazo",
  "interveniente_quitante",
  "parcela",
  "ja_quitado",
];
export const CORRETAGEM_CONTRATANTES: CorretagemContratantes[] = [
  "vendedores",
  "compradores",
  "partes",
];

export const POSSE_MARCO_LABELS: Record<PosseMarco, string> = {
  assinatura: "Na assinatura",
  parcela: "No pagamento de uma parcela",
  protocolo_registro: "No protocolo do registro",
};

export const ONUS_QUITACAO_LABELS: Record<OnusQuitacao, string> = {
  compradores_prazo: "Compradores quitam, em prazo",
  interveniente_quitante: "Interveniente quitante",
  parcela: "Quitado com uma parcela",
  ja_quitado: "Já quitado",
};

export const CORRETAGEM_CONTRATANTES_LABELS: Record<CorretagemContratantes, string> = {
  vendedores: "Vendedores",
  compradores: "Compradores",
  partes: "Ambas as partes",
};

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
  termos: NegociacaoTermos;
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
  /** Migration 114. */
  dispara_corretagem?: boolean;
  /** Migration 114. `tipo === "permuta"` only. */
  permuta_ativo_ids?: string[];
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

/** `pessoa_tipo`/`documento`/... are OPTIONAL, and omitting a key is not the
 *  same as sending it `null`: the service infers `pessoa_tipo` from
 *  `documento` only when the `pessoa_tipo` KEY IS ABSENT from the JSON body
 *  (`"pessoa_tipo" not in valores` — see `negociacao_estruturada_service
 *  ._normalizar_qualificacao`). Sending `pessoa_tipo: null` explicitly BLOCKS
 *  that inference. The form builds this payload accordingly — see
 *  `NegociacaoEstruturadaPanel.IntermediarioFormDialog`. */
export interface IntermediarioCreate extends Partial<IntermediarioQualificacao> {
  corretor_id?: string | null;
  nome: string;
  creci?: string | null;
  /** Defaults server-side to "percentual". */
  tipo?: IntermediarioTipo;
  valor?: string | null;
  /** Defaults server-side to "intermediario". See `IntermediarioNatureza`. */
  natureza?: IntermediarioNatureza;
  papel?: string | null;
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
  fgts: "FGTS (legado — junte ao financiamento)",
  saldo: "Saldo",
  direta: "Direta",
  permuta: "Permuta",
};

export const INTERMEDIARIO_TIPO_LABELS: Record<IntermediarioTipo, string> = {
  percentual: "Percentual",
  valor_fixo: "Valor fixo",
};
