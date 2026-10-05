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
  /** The stored file is a human's manual upload (not a live emission). */
  arquivo_manual: boolean;
  /** A PDF sits in our bucket (upload OR live receipt) — "Reler" can
   *  re-extract it with the current reader. Optional for older payloads. */
  pode_reler?: boolean;
  /** The last re-read: in flight, and what it found but did not write. */
  releitura?: CertidaoReleitura | null;
  arquivo_nome: string | null;
  origem: "api" | "ia" | "manual" | null;
  confirmado: boolean;
  analise_ia: string | null;
  erro_mensagem: string | null;
  /** The Receita refused a NEW certidão (holder of a valid "positiva com efeitos
   *  de negativa"): this is its 2ª via, so `emitida_em` is the ORIGINAL date. */
  segunda_via: boolean;
  /** Receita "positiva com efeitos de negativa" 2ª via ONLY (owner 2026-10-01):
   *  judged by the PRINTED validity, and the operator must acknowledge it. */
  pcen: CertidaoPcen | null;
  /** PENDING for a reason an operator can fix — not an error. `credencial_govbr`:
   *  Dívida Ativa SP needs the office's GOV.BR login; `erro_mensagem` carries the
   *  pt-BR text. The cell stays uploadable (Enviar PDF). */
  pendencia?: "credencial_govbr" | null;
}

export type CampoEstruturado = "numero" | "emitida_em" | "validade_ate" | "resultado";

/** A value the re-read found but did not write — the stored one is a
 *  human's (confirmed/typed) or the registry's. A human decides. */
export interface CertidaoDivergencia {
  campo: CampoEstruturado;
  valor_atual: string | null;
  valor_lido: string;
}

export interface CertidaoReleitura {
  em_andamento: boolean;
  concluida_em: string | null;
  divergencias: CertidaoDivergencia[];
}

export interface CertidaoPcen {
  titulo: string;
  /** The one-line aviso (also on the contract readiness). */
  mensagem: string;
  /** Plain-language explanation, one paragraph per entry. */
  explicacao: string[];
  validade_ate: string;
  /** The printed validity already passed. */
  vencida: boolean;
  ciente: boolean;
  ciente_em: string | null;
  duvida_em: string | null;
  acoes: { entendi: string; duvida: string };
}

/** The org's configured contact for questions — `null` when none is set. */
export interface SuporteContato {
  nome: string | null;
  email: string | null;
  whatsapp: string | null;
}

export interface CienciaPcenResult {
  resultado_id: string;
  acao: "entendi" | "duvida";
  pcen: CertidaoPcen;
  suporte: SuporteContato | null;
}

export interface CertidaoParteTotais {
  nao_constam: number;
  constam: number;
  pendente: number;
  vencidas: number;
}

export type CertidaoGrupo = "comprador" | "vendedor" | "antigo_proprietario";

export interface CertidaoParte {
  /** `c:<cliente_id>` | `e:<empresa_id>` */
  chave: string;
  kind: "pessoa" | "empresa";
  tipo_pessoa: "PF" | "PJ";
  /** `COMP n` | `VEND n` | `EMP n` */
  rotulo: string;
  lado: "comprador" | "vendedor" | null;
  /** Explicit group (contract §1) — subtabs split on THIS, never on `papel`/`rotulo`. */
  grupo: CertidaoGrupo;
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

/** `POST /api/clientes/{cliente_id}/certidoes/reler` — counts at request time;
 *  the readings themselves run in the background. */
export interface RelerCertidoesResponse {
  relidos: number;
  sem_arquivo: number;
  em_andamento: number;
  erros: number;
}

// ─── Antigos proprietários (antigos-proprietarios-CONTRACT.md §2–§5) ──────────

export type AntigosMotivo =
  | "transferencia_menos_de_5_anos"
  | "transferencia_5_anos_ou_mais"
  | "sem_transferencia_registrada"
  | "ultima_transferencia_desconhecida"
  | "sem_imovel";

export interface AntigosEstado {
  atendimento_id: string;
  /** `null` = unknown. */
  exigido: boolean | null;
  motivo: AntigosMotivo | null;
  janela_anos: number;
  ultima_transferencia: {
    ato_id: string | null;
    ato_ref: string | null;
    natureza: string | null;
    data_registro: string | null;
    detalhes_origem: string | null;
  } | null;
  origem_dados: "titulo_confirmado" | "extracao" | "manual" | null;
  transmitentes: {
    nome: string;
    documento_mascarado: string | null;
    tipo_pessoa: "PF" | "PJ";
    ja_no_card: boolean;
  }[];
  dispensado: { em: string; por: { id: string; nome: string | null }; motivo: string } | null;
  sincronizacao_pendente: number;
}

export interface AntigosEmissao {
  parte_id: string;
  status: "solicitada" | "nao_iniciada";
  codigo: "DOCUMENTO_AUSENTE" | "CREDENCIAIS_AUSENTES" | null;
  consulta_id: string | null;
}

export interface AntigosSincronizacao {
  atendimento_id: string;
  criados: { parte_id: string; nome: string; tipo_pessoa: "PF" | "PJ" }[];
  ja_no_card: { nome: string; documento_mascarado: string | null }[];
  emissoes: AntigosEmissao[];
  ignorado: "dispensado" | "sem_imovel" | "matricula_nao_nomeia_antigos" | "transferencia_5_anos_ou_mais" | null;
}

/** Person `{nome, cpf}` XOR company `{cnpj, razao_social?}`. */
export interface AntigoCriarInput {
  nome?: string;
  cpf?: string;
  cnpj?: string;
  razao_social?: string;
}

export interface AntigoCriarResponse {
  parte: CertidaoParte;
  emissao: AntigosEmissao | null;
}
