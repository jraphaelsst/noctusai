/**
 * Proposta (lead-to-contract CONTRACT §4 + §7.3 + addendum). Money stays a
 * decimal STRING end to end (same rule as `negociacaoEstruturada`).
 */
import type { ParcelaTipo } from "@/types/negociacaoEstruturada";

export type PropostaStatus = "rascunho" | "enviada" | "aceita" | "recusada" | "cancelada";

export const PROPOSTA_STATUS_LABELS: Record<PropostaStatus, string> = {
  rascunho: "Rascunho",
  enviada: "Enviada",
  aceita: "Aceita",
  recusada: "Recusada",
  cancelada: "Cancelada",
};

/** Editable only while the proposta is still open. */
export const propostaEditavel = (s: PropostaStatus): boolean =>
  s === "rascunho" || s === "enviada";

/** `ParcelaIn` snapshot row. `favorecido_ref` is a client key ("fav:0"). */
export interface PropostaParcela {
  tipo: ParcelaTipo;
  valor: string;
  vencimento?: string | null;
  evento?: string | null;
  forma_pagamento?: string | null;
  favorecido_ref?: string | null;
  confissao_divida?: boolean;
  dispara_corretagem?: boolean;
}

export interface PropostaFavorecido {
  nome: string;
  cpf_cnpj?: string | null;
  banco?: string | null;
  agencia?: string | null;
  conta?: string | null;
  pix?: string | null;
}

export interface PropostaIntermediario {
  nome: string;
  creci?: string | null;
  tipo?: "percentual" | "valor_fixo";
  valor?: string | null;
  papel?: string | null;
}

export interface PropostaTermos {
  posse_prazo_dias?: number | null;
  posse_multa_diaria?: string | null;
  ad_corpus?: boolean | null;
  itens_integrantes?: string | null;
  onus_quitacao?: string | null;
  onus_prazo_dias?: number | null;
  confissao_juros_am?: string | null;
  confissao_garantia?: string | null;
  corretagem_contratantes?: string | null;
  clausulas_extras?: Record<string, { texto: string; modo: "acrescentar" | "substituir" }>;
  [k: string]: unknown;
}

export interface Proposta {
  id: string;
  atendimento_id: string;
  cliente_id: string;
  visita_id: string | null;
  imovel_codigo: string;
  status: PropostaStatus;
  valor_proposto: string | null;
  pct_comissao: string | null;
  financiamento: boolean | null;
  fgts: boolean | null;
  validade_ate: string | null;
  observacoes: string | null;
  parcelas: PropostaParcela[];
  favorecidos: PropostaFavorecido[];
  intermediarios: PropostaIntermediario[];
  termos: PropostaTermos;
  imobiliaria_id: string | null;
  testemunha_ids: string[];
  enviada_em: string | null;
  aceita_em: string | null;
  recusada_em: string | null;
  motivo_recusa: string | null;
  contrato_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  imovel: { codigo: string; titulo: string | null; endereco: string | null };
  visita: { id: string; data_visita: string | null } | null;
  imobiliaria: { id: string; razao_social: string | null } | null;
  testemunhas: { id: string; nome: string }[];
  saldo_nao_alocado: string | null;
  completude: string[];
}

/** PATCH body: any editable field. */
export type PropostaPatch = Partial<
  Pick<
    Proposta,
    | "valor_proposto"
    | "pct_comissao"
    | "financiamento"
    | "fgts"
    | "validade_ate"
    | "observacoes"
    | "parcelas"
    | "favorecidos"
    | "intermediarios"
    | "termos"
    | "imobiliaria_id"
    | "testemunha_ids"
  >
>;

export interface PropostaCreateBody {
  visita_id?: string;
  imovel_codigo?: string;
}

export type CertidaoPosAceiteStatus = "emitindo" | "ja_valida" | "pulada" | "bloqueado" | "erro";
export type MatriculaPosAceiteStatus = "extraindo" | "ok" | "faltando" | "erro";

export interface PosAceite {
  certidoes: {
    parte_nome: string;
    kind: string;
    alvo_id: string;
    consulta_id: string | null;
    status: CertidaoPosAceiteStatus;
    motivo: string | null;
    tipos: string[];
  }[];
  matricula: {
    status: MatriculaPosAceiteStatus;
    documento_id: string | null;
    motivo: string | null;
  };
}

export type AceitePassoNome =
  | "materializar"
  | "visita"
  | "contrato"
  | "status"
  | "funil"
  | "pos_aceite";

export interface AceitePasso {
  passo: AceitePassoNome;
  status: "ok" | "erro" | "pulado";
  mensagem: string | null;
}

export interface AceiteResponse {
  proposta: Proposta;
  contrato_id: string | null;
  geracao: { pronto: boolean; faltando: unknown[]; bloqueios: unknown[]; avisos: unknown[] };
  passos?: AceitePasso[];
  pos_aceite?: PosAceite | null;
}

export const ACEITE_PASSO_LABELS: Record<AceitePassoNome, string> = {
  materializar: "Aplicar a negociação",
  visita: "Registrar na visita",
  contrato: "Criar o rascunho do contrato",
  status: "Marcar proposta como aceita",
  funil: "Atualizar o funil",
  pos_aceite: "Certidões e matrícula",
};

/** Friendly pt-BR copy for the contract's 409 codes (addendum). */
export const PROPOSTA_ERRO_409: Record<string, string> = {
  proposta_fechada: "Esta proposta já foi encerrada e não pode mais ser alterada.",
  proposta_ja_aceita: "Já existe uma proposta aceita neste atendimento.",
  imovel_divergente:
    "O imóvel desta proposta é diferente do imóvel já em negociação neste atendimento.",
  visita_nao_realizada: "A visita ainda não foi marcada como realizada.",
};
