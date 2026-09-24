/**
 * Certidões matriz — the "Certidões" card tab's grid (Levantamento de
 * Certidões.xlsx, first tab): every certidão TYPE crossed with every
 * vendedor party + their PJ-requiring empresas, aggregated server-side by
 * `card_hub.certidoes_matriz_service.montar_matriz`.
 */

/** One cell's color — GREEN "Não constam" / RED "Constam" / YELLOW
 *  "Pendente" / grey "N/A" (the FGTS row on every PF column). Text is
 *  ALWAYS kept alongside the color (`texto`) — never color alone. */
export type CertidaoMatrizCelulaStatus = "nao_constam" | "constam" | "pendente" | "na";

export interface CertidaoMatrizCelula {
  status: CertidaoMatrizCelulaStatus;
  texto: string;
  resultado_id: string | null;
  consulta_id: string | null;
  numero: string | null;
  emitida_em: string | null; // YYYY-MM-DD
  validade_ate: string | null; // YYYY-MM-DD
  analise_ia: string | null;
  erro_mensagem: string | null;
}

/** A column — one vendedor party ("VEND n") or one of their PJ-requiring
 *  empresas ("EMP n"). `certidoesMatrizColunaProps` below turns this into
 *  the `CertidoesPartePanel` scope prop pair. */
export interface CertidaoMatrizColuna {
  kind: "pessoa" | "empresa";
  id: string;
  rotulo: string; // "VEND 1" | "EMP 1"
  nome: string;
  papel?: string;
  cnpj?: string | null;
}

export interface CertidaoMatrizLinha {
  tipo: string;
  linha: string; // "5.1".."5.15"
  rotulo: string;
}

/** `totais[coluna_id]` — per-column counts across the 15 rows (never per
 *  row across columns), mirroring the Excel source's "Totais" footer. An
 *  N/A cell (FGTS on a PF column) never counts toward any bucket. */
export interface CertidaoMatrizTotais {
  nao_constam: number;
  constam: number;
  pendente: number;
}

/** `GET /api/clientes/{cliente_id}/certidoes/matriz`. Card route — a raw
 *  dict, not the `success_response()` envelope the `/api/certidoes/*`
 *  family uses (same convention `EmpresasDoCardResponse` documents). */
export interface CertidoesMatrizResponse {
  atendimento_id: string | null;
  data_levantamento: string; // YYYY-MM-DD
  linhas: CertidaoMatrizLinha[];
  colunas: CertidaoMatrizColuna[];
  /** `celulas[tipo][coluna_id]`. */
  celulas: Record<string, Record<string, CertidaoMatrizCelula>>;
  totais: Record<string, CertidaoMatrizTotais>;
}
