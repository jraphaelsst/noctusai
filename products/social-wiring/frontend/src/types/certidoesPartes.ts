/**
 * Certidões per party — wire types for `GET /api/clientes/{cliente_id}/
 * certidoes/partes` and its write siblings. Mirror of
 * `projects/atendimento-partes-imoveis-CONTRACT.md` §1 1:1 (snake_case kept,
 * no camelCase mapping).
 */
import type { CertidaoMatrizLinha } from "@/types/certidoesMatriz";

export type CelulaStatus = "nao_constam" | "constam" | "pendente" | "na";

export type CelulaStatusProcessamento =
  | "pendente"
  | "processando"
  | "na_fila"
  | "sucesso"
  | "erro";

export type CelulaResultado =
  | "negativa"
  | "positiva"
  | "positiva_com_efeito_de_negativa"
  | "nao_emitida"
  | "negativa_com_homonimos";

export interface CertidaoParteCelula {
  status: CelulaStatus;
  texto: string;
  tipo: string | null;
  resultado_id: string | null;
  consulta_id: string | null;
  status_processamento: CelulaStatusProcessamento | null;
  resultado: CelulaResultado | null;
  numero: string | null;
  emitida_em: string | null;
  validade_ate: string | null;
  idade_dias: number | null;
  stale_para_contrato: boolean;
  arquivo_url: string | null;
  tem_arquivo: boolean;
  arquivo_nome: string | null;
  origem: "api" | "ia" | "manual" | null;
  confirmado: boolean;
  analise_ia: string | null;
  erro_mensagem: string | null;
}

export interface CertidaoParteTotais {
  nao_constam: number;
  constam: number;
  pendente: number;
  vencidas: number;
}

export interface CertidaoParte {
  /** `c:<cliente_id>` | `e:<empresa_id>` */
  chave: string;
  kind: "pessoa" | "empresa";
  tipo_pessoa: "PF" | "PJ";
  /** `COMP n` | `VEND n` | `EMP n` */
  rotulo: string;
  lado: "comprador" | "vendedor" | null;
  papel: string;
  titular: boolean;
  nome: string;
  /** digits only: CPF(11) | CNPJ(14) */
  documento: string | null;
  cliente_id: string | null;
  empresa_id: string | null;
  parte_id: string | null;
  totais: CertidaoParteTotais;
  celulas: Record<string, CertidaoParteCelula>;
}

/** Same shape/semantics as the matriz linha (fixed 5.1–5.13 + custom rows). */
export type CertidaoParteLinha = CertidaoMatrizLinha;

export interface CertidoesPartesResponse {
  atendimento_id: string | null;
  /** `YYYY-MM-DD` — the date `idade_dias`/`stale_para_contrato` are measured at. */
  data_referencia: string;
  max_dias: number;
  linhas: CertidaoParteLinha[];
  partes: CertidaoParte[];
}

export interface EmissaoResponse {
  consulta_id: string;
  resultados: { resultado_id: string; tipo: string; status_processamento: "pendente" }[];
}

export interface CelulaEnsureResponse {
  resultado_id: string;
  consulta_id: string;
  criado: boolean;
}

export interface SolicitarEmissaoInput {
  kind: "pessoa" | "empresa";
  alvoId: string;
  /** `null` ⇒ every automated tipo applicable to the party. */
  tipos: string[] | null;
}

export interface UploadCelulaInput {
  kind: "pessoa" | "empresa";
  alvoId: string;
  linhaChave: string;
  file: File;
}
