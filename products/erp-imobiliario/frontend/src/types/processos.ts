/**
 * Processo de Venda — the post-proposal execution board's card entity.
 *
 * Mirrors the backend DTO whitelist in
 * `backend/app/services/processos_venda_service.py::_PROCESSO_DTO_FIELDS`.
 */

/**
 * The 8 execution stages, in order. A FIXED vocabulary mirroring
 * `erp.etapa_processo` — deliberately not configurable (roadmap anti-goal:
 * `etapa_processo` is not a generic workflow engine).
 */
export type EtapaProcesso =
  | 'elaboracao_contrato'
  | 'analise_partes'
  | 'revisao_contrato'
  | 'assinatura'
  | 'financiamento_escritura'
  | 'finalizacao'
  | 'entrega_chaves'
  | 'nota_fiscal';

export interface ProcessoVenda {
  id: string;
  cliente_id: string;
  negociacao_venda_id: string;
  corretor_id: string;
  etapa: EtapaProcesso;
  valor: number;
  observacoes?: string | null;
  kanban_pos: number;
  arquivado: boolean;
  created_at: string;
  updated_at: string;
  cliente?: {
    id: string;
    nome: string;
    email?: string | null;
    telefone?: string | null;
  };
  corretor?: {
    id: string;
    nome: string;
    email?: string | null;
  };
  /** The deal this execution came from. */
  negociacao?: {
    id: string;
    titulo?: string | null;
    valor_estimado: number;
    closed_at?: string | null;
  };
}

/** One kanban column of the Processos board. */
export interface ColunaProcessos {
  etapa: EtapaProcesso;
  total: number;
  valorTotal: number;
  cards: ProcessoVenda[];
}
