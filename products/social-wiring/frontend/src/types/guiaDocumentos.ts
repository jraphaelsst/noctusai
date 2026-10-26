/**
 * `GET /api/guia-documentos` — the one place that says which data each
 * document supplies, what each certidão needs, and what each lead-flow stage
 * demands. Derived server-side from the code catalogs at request time (FONTES,
 * ROTULOS_TIPO_DOCUMENTO, documento_checklist_service.ITENS, the certidão
 * catalog, atendimento_blocos BLOCOS) — never a hand-kept copy. pt-BR labels.
 *
 * Contract: projects scratchpad `guia-contract.md` (sw-guia-documentos).
 * Response is the bare payload (no `{data}` envelope).
 */
export interface GuiaCampo {
  campo: string;
  rotulo: string;
}

export interface GuiaDocumento {
  /** FONTES key, e.g. "rg", "cnh", "certidao_casamento". */
  tipo_documento: string;
  rotulo: string;
  campos: GuiaCampo[];
  /** e.g. "leitura de todas as páginas". */
  observacao: string | null;
  /** Where those fields go ("Qualificação no contrato", …). */
  usos: string[];
}

/** Reverse index: field → the documents that supply it. */
export interface GuiaCampoIndice {
  campo: string;
  rotulo: string;
  /** `tipo_documento[]`, in the readiness "Envie …" suggestion order. */
  documentos: string[];
}

export interface GuiaCertidaoRequisito {
  documento: "cpf" | "cnpj";
  campos: GuiaCampo[];
}

export interface GuiaCertidao {
  tipo: string;
  /** Catalog line, e.g. "5.1". */
  linha: string;
  rotulo: string;
  fonte: "infosimples" | "manual";
  requisitos: GuiaCertidaoRequisito[];
  credencial: "govbr" | null;
  observacao: string | null;
}

export interface GuiaEtapaExigencia {
  rotulo: string;
  tipo: "campo" | "documento" | "certidao";
  ref: string;
}

export interface GuiaEtapa {
  chave: string;
  rotulo: string;
  /** atendimento_blocos BLOCOS owner. */
  bloco: string | null;
  exige: GuiaEtapaExigencia[];
  observacao: string | null;
}

export interface GuiaDadoObrigatorio {
  chave: string;
  rotulo: string;
  documentos: string[];
  escopo: string | null;
  dica: string | null;
}

export interface GuiaDocumentos {
  /** Hash of the payload, for cache busting. */
  versao: string;
  documentos: GuiaDocumento[];
  campos: GuiaCampoIndice[];
  certidoes: GuiaCertidao[];
  etapas: GuiaEtapa[];
  dados_obrigatorios: GuiaDadoObrigatorio[];
}
