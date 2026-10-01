/**
 * Parties of an atendimento (contract §2 — `atendimento-partes-imoveis-CONTRACT.md`).
 * Snake_case kept 1:1 with the wire. Owned by FE-leads-partes.
 */

export type TipoPessoa = "PF" | "PJ";
export type LadoParteContrato = "comprador" | "vendedor";

export interface ParteEmpresaResumo {
  id: string;
  razao_social: string | null;
  nome_fantasia: string | null;
  cnpj: string | null;
  situacao_cadastral: string | null;
}

/** §2.1 `ParteItem`. `cliente` carries the `_CLIENTE_RESUMO` keys (loose here:
 *  this slice only reads a few of them). */
export interface ParteItem {
  parte_id: string | null;
  titular: boolean;
  rotulo: string;
  lado: LadoParteContrato;
  papel: string;
  ordem: number;
  tipo_pessoa: TipoPessoa;
  cliente_id: string | null;
  empresa_id: string | null;
  nome: string;
  documento: string | null;
  observacao: string | null;
  cliente: Record<string, unknown> | null;
  empresa: ParteEmpresaResumo | null;
}

export interface PartesResponse {
  items: ParteItem[];
  total: number;
  atendimento_id: string | null;
}

/** §2.3 body (`ParteCreateBody`): exactly ONE of cliente_id / nome / empresa_id / cnpj. */
export interface ParteCreateBody {
  cliente_id?: string;
  nome?: string;
  celular?: string;
  empresa_id?: string;
  cnpj?: string;
  razao_social?: string;
  papel?: string;
  observacao?: string;
  atendimento_id?: string;
  lado?: LadoParteContrato;
}

export interface ParteLookupAtendimento {
  id: string;
  titulo: string | null;
  etapa: { id: string; nome: string } | null;
  status: string | null;
  arquivado: boolean;
  lado: LadoParteContrato | null;
  papel: string | null;
  titular: boolean;
  parte_id: string | null;
}

export interface ParteLookupCertidaoItem {
  tipo: string;
  rotulo: string;
  resultado_id: string;
  emitida_em: string | null;
  validade_ate: string | null;
  idade_dias: number | null;
  stale_para_contrato: boolean;
  resultado: string | null;
}

/** §2.5 response. A lookup miss is a 200 with `encontrado: null`. */
export interface ParteLookup {
  documento: string;
  tipo_documento: "cpf" | "cnpj";
  encontrado: "cliente" | "empresa" | null;
  cliente: {
    id: string;
    nome: string | null;
    nome_oficial: string | null;
    cpf: string | null;
    celular: string | null;
    email: string | null;
  } | null;
  empresa: ParteEmpresaResumo | null;
  ja_no_atendimento: boolean;
  atendimentos: ParteLookupAtendimento[];
  certidoes: {
    max_dias: number;
    data_referencia: string;
    itens: ParteLookupCertidaoItem[];
    tipos_vencidos: string[];
    alerta_vencidas: boolean;
    mensagem: string | null;
  };
}

/** §1.2 response (201). */
export interface EmissaoCertidoesResponse {
  consulta_id: string;
  resultados: { resultado_id: string; tipo: string; status_processamento: string }[];
}
